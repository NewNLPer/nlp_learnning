import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F

from torchtext.datasets import Multi30k
from torchtext.data import Field, BucketIterator

import spacy
import numpy as np

import random
import math
import time

"""Set the random seeds for reproducability."""

SEED = 1234

random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)
torch.cuda.manual_seed(SEED)
torch.backends.cudnn.deterministic = True

"""Load the German and English spaCy models."""

spacy_de = spacy.load('de_core_news_sm')
spacy_en = spacy.load('en_core_web_sm')
"""We create the tokenizers."""

def tokenize_de(text):
    # Tokenizes German text from a string into a list of strings
    return [tok.text for tok in spacy_de.tokenizer(text)]

def tokenize_en(text):
    # Tokenizes English text from a string into a list of strings
    return [tok.text for tok in spacy_en.tokenizer(text)]

"""The fields remain the same as before."""

SRC = Field(tokenize = tokenize_de,
            init_token = '<sos>',
            eos_token = '<eos>',
            lower = True)

TRG = Field(tokenize = tokenize_en,
            init_token = '<sos>',
            eos_token = '<eos>',
            lower = True)

"""Load the data."""

train_data, valid_data, test_data = Multi30k.splits(exts = ('.de', '.en'),fields = (SRC, TRG))

"""Build the vocabulary."""

SRC.build_vocab(train_data, min_freq = 2)
TRG.build_vocab(train_data, min_freq = 2)

"""Define the device."""

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

"""Create the iterators."""

BATCH_SIZE = 128
train_iterator, valid_iterator, test_iterator = BucketIterator.splits(
    (train_data, valid_data, test_data),
    batch_size = BATCH_SIZE,
    device = device)






class Encoder(nn.Module):
    def __init__(self, input_dim, emb_dim, enc_hid_dim, dec_hid_dim, dropout):
        super().__init__()
        self.embedding = nn.Embedding(input_dim, emb_dim)
        self.rnn = nn.GRU(emb_dim, enc_hid_dim, bidirectional = True)
        self.fc = nn.Linear(enc_hid_dim * 2, dec_hid_dim)
        self.dropout = nn.Dropout(dropout)
    def forward(self, src):
        '''
        src = [src_len, batch_size]
        '''
        src = src.transpose(0, 1)
        # src = [batch_size, src_len]
        embedded = self.dropout(self.embedding(src)).transpose(0, 1)
        # embedded = [src_len, batch_size, emb_dim]
        enc_output, enc_hidden = self.rnn(embedded) # if h_0 is not give, it will be set 0 acquiescently
        # enc_output = [src_len, batch_size, 2*enc_hid_dim]
        # enc_hidden = [2, batch_size, enc_hid_dim]

        # enc_hidden is stacked [forward_1, backward_1, forward_2, backward_2, ...]
        # enc_output are always from the last layer

        # enc_hidden [-2, :, : ] is the last of the forwards RNN
        # enc_hidden [-1, :, : ] is the last of the backwards RNN

        #[2, batch_size, enc_hid_dim]----------->->->[batch_size,2*enc_hid_dim]
        s = torch.tanh(self.fc(torch.cat((enc_hidden[-2,:,:], enc_hidden[-1,:,:]), dim = 1)))#[2, batch_size, enc_hid_dim]---》[batch_size,2*enc_hid_dim]
        # enc_output = [src_len, batch_size, 2*enc_hid_dim] 每个时刻双向的隐藏层
        # s = [batch_size, dec_hid_dim] 最后一个时刻的前向与后向的拼接
        return enc_output, s


class Attention(nn.Module):
    def __init__(self, enc_hid_dim, dec_hid_dim):
        super().__init__()
        self.attn = nn.Linear((enc_hid_dim * 2) + dec_hid_dim, dec_hid_dim, bias=False)
        self.v = nn.Linear(dec_hid_dim, 1, bias = False)

    def forward(self, s, enc_output):

        # s = [batch_size, dec_hid_dim]
        # enc_output = [src_len, batch_size, enc_hid_dim * 2]
        src_len = enc_output.shape[0]
        # repeat decoder hidden state src_len times
        # s = [batch_size, src_len, dec_hid_dim]
        # enc_output = [batch_size, src_len, enc_hid_dim * 2]
        s = s.unsqueeze(1).repeat(1, src_len, 1)
        enc_output = enc_output.transpose(0, 1)

        energy = torch.tanh(self.attn(torch.cat((s, enc_output), dim = 2)))
        # energy = [batch_size, src_len, dec_hid_dim]
        attention = self.v(energy).squeeze(2)

        # attention = [batch_size, src_len]
        return F.softmax(attention, dim=1)###返回二维矩阵，称为 a ，其每一行的和都是1，每一行都是一个权重分布


class Decoder(nn.Module):
    def __init__(self, output_dim, emb_dim, enc_hid_dim, dec_hid_dim, dropout, attention):
        super().__init__()
        self.output_dim = output_dim
        self.attention = attention
        self.embedding = nn.Embedding(output_dim, emb_dim)
        self.rnn = nn.GRU((enc_hid_dim * 2) + emb_dim, dec_hid_dim)
        self.fc_out = nn.Linear((enc_hid_dim * 2) + dec_hid_dim + emb_dim, output_dim)
        self.dropout = nn.Dropout(dropout)

    def forward(self, dec_input, s, enc_output):
        # dec_input = [batch_size]
        # s = [batch_size, dec_hid_dim]
        # enc_output = [src_len, batch_size, enc_hid_dim * 2]
        dec_input = dec_input.unsqueeze(1) # dec_input = [batch_size, 1]
        embedded = self.dropout(self.embedding(dec_input)).transpose(0, 1) # embedded = [1, batch_size, emb_dim]
        ###Decode的输入就是每次只控制输入一个单词
        a = self.attention(s, enc_output).unsqueeze(1)
        # a = [batch_size, 1, src_len]
        enc_output = enc_output.transpose(0, 1)
        # enc_output = [batch_size, src_len, enc_hid_dim * 2]
        c = torch.bmm(a, enc_output).transpose(0, 1)
        # c = [1, batch_size, enc_hid_dim * 2]
        rnn_input = torch.cat((embedded, c), dim = 2)
        # rnn_input = [1, batch_size, (enc_hid_dim * 2) + emb_dim]
        dec_output, dec_hidden = self.rnn(rnn_input, s.unsqueeze(0))
        # dec_output = [src_len(==1), batch_size, dec_hid_dim]
        # dec_hidden = [1, batch_size, dec_hid_dim] 新的来进行下一次迭代
        embedded = embedded.squeeze(0)
        dec_output = dec_output.squeeze(0)
        c = c.squeeze(0)
        # embedded = [batch_size, emb_dim]
        # dec_output = [batch_size, dec_hid_dim]
        # c = [batch_size, enc_hid_dim * 2]
        pred = self.fc_out(torch.cat((dec_output, c, embedded), dim = 1))
        # pred = [batch_size, output_dim]
        return pred, dec_hidden.squeeze(0)



class Seq2Seq(nn.Module):
    def __init__(self, encoder, decoder, device):
        super().__init__()
        self.encoder = encoder
        self.decoder = decoder
        self.device = device

    def forward(self, src, trg, teacher_forcing_ratio = 0.5):

        # src = [src_len, batch_size] 德语
        # trg = [trg_len, batch_size] 英语
        # teacher_forcing_ratio is probability to use teacher forcing

        batch_size = src.shape[1]
        trg_len = trg.shape[0]

        trg_vocab_size = self.decoder.output_dim

        # tensor to store decoder outputs

        outputs = torch.zeros(trg_len, batch_size, trg_vocab_size).to(self.device)

        # enc_output is all hidden states of the input sequence, back and forwards
        # s is the final forward and backward hidden states, passed through a linear layer
        enc_output, s = self.encoder(src)

        # first input to the decoder is the <sos> tokens
        dec_input = trg[0,:]

        for t in range(1, trg_len):

            # insert dec_input token embedding, previous hidden state and all encoder hidden states
            # receive output tensor (predictions) and new hidden state
            dec_output, s = self.decoder(dec_input, s, enc_output)

            # place predictions in a tensor holding predictions for each token
            outputs[t] = dec_output

            # decide if we are going to use teacher forcing or not
            teacher_force = random.random() < teacher_forcing_ratio

            # get the highest predicted token from our predictions
            top1 = dec_output.argmax(1)

            # if teacher forcing, use actual next token as next input
            # if not, use predicted token
            dec_input = trg[t] if teacher_force else top1

        return outputs



INPUT_DIM = len(SRC.vocab)
OUTPUT_DIM = len(TRG.vocab)
ENC_EMB_DIM = 256
DEC_EMB_DIM = 256
ENC_HID_DIM = 512
DEC_HID_DIM = 512
ENC_DROPOUT = 0.5
DEC_DROPOUT = 0.5

attn = Attention(ENC_HID_DIM, DEC_HID_DIM)
enc = Encoder(INPUT_DIM, ENC_EMB_DIM, ENC_HID_DIM, DEC_HID_DIM, ENC_DROPOUT)
dec = Decoder(OUTPUT_DIM, DEC_EMB_DIM, ENC_HID_DIM, DEC_HID_DIM, DEC_DROPOUT, attn)

model = Seq2Seq(enc, dec, device).to(device)
TRG_PAD_IDX = TRG.vocab.stoi[TRG.pad_token]
criterion = nn.CrossEntropyLoss(ignore_index = TRG_PAD_IDX).to(device)
###设置ignore_index = TRG_PAD_IDX的含义就是，对于填充词不需要进行交叉熵的计算

optimizer = optim.Adam(model.parameters(), lr=1e-3)

"""We then create the training loop..."""

def train(model, iterator, optimizer, criterion):
    model.train()
    epoch_loss = 0
    for i, batch in enumerate(iterator):
        src = batch.src
        trg = batch.trg # trg = [trg_len, batch_size]

        pred = model(src, trg)      # pred = [trg_len, batch_size, pred_dim]
        pred_dim = pred.shape[-1]

        trg = trg[1:].view(-1)
        pred = pred[1:].view(-1, pred_dim)
        # trg = [(trg len - 1) * batch size]
        # pred = [(trg len - 1) * batch size, pred_dim]

        loss = criterion(pred, trg)
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        epoch_loss += loss.item()

    return epoch_loss / len(iterator)

"""...and the evaluation loop, remembering to set the model to `eval` mode and turn off teaching forcing."""

def evaluate(model, iterator, criterion):
    model.eval()
    epoch_loss = 0
    with torch.no_grad():
        for i, batch in enumerate(iterator):
            src = batch.src
            trg = batch.trg # trg = [trg_len, batch_size]

            # output = [trg_len, batch_size, output_dim]
            output = model(src, trg, 0) # turn off teacher forcing

            output_dim = output.shape[-1]

            # trg = [(trg_len - 1) * batch_size]
            # output = [(trg_len - 1) * batch_size, output_dim]
            output = output[1:].view(-1, output_dim)
            trg = trg[1:].view(-1)

            loss = criterion(output, trg)
            epoch_loss += loss.item()

    return epoch_loss / len(iterator)

"""Finally, define a timing function."""

def epoch_time(start_time, end_time):
    elapsed_time = end_time - start_time
    elapsed_mins = int(elapsed_time / 60)
    elapsed_secs = int(elapsed_time - (elapsed_mins * 60))
    return elapsed_mins, elapsed_secs

"""Then, we train our model, saving the parameters that give us the best validation loss."""

best_valid_loss = float('inf')

for epoch in range(100):
    start_time = time.time()

    train_loss = train(model, train_iterator, optimizer, criterion)
    valid_loss = evaluate(model, valid_iterator, criterion)

    end_time = time.time()

    epoch_mins, epoch_secs = epoch_time(start_time, end_time)

    if valid_loss < best_valid_loss:
        best_valid_loss = valid_loss
        torch.save(model.state_dict(), 'tut3-model.pt')

    print(f'Epoch: {epoch+1:02} | Time: {epoch_mins}m {epoch_secs}s')
    print(f'\tTrain Loss: {train_loss:.3f} | Train PPL: {math.exp(train_loss):7.3f}')
    print(f'\t Val. Loss: {valid_loss:.3f} |  Val. PPL: {math.exp(valid_loss):7.3f}')

"""Finally, we test the model on the test set using these "best" parameters."""

model.load_state_dict(torch.load('tut3-model.pt'))

test_loss = evaluate(model, test_iterator, criterion)

print(f'| Test Loss: {test_loss:.3f} | Test PPL: {math.exp(test_loss):7.3f} |')

