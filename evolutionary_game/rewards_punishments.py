# -*- coding: utf-8 -*-
"""
@author: NewNLPer
@time: 2023/12/11 19:07
coding with comment！！！
"""

import matplotlib.pyplot as plt
import numpy as np
from scipy.integrate import odeint
from tqdm import tqdm

def Cooperation_proportion_derivatives(x, t, punish, b, xi):
    """
    :param x:  Initial variable[x,rp]
    :param t: time
    :param punish:
    :param b: b=[1,2]
    :param xi:Growth rate control
    :return:
    """

    ### D + rp * P
    # piC = x[0] + (x[1] * punish) * (1 - x[0])
    # piD = (b - x[1] * punish) * x[0]
    ### D - rp * D + rp*P
    piC = (1 - x[1]) * x[0] + x[2] * punish * (1 - x[0])
    piD = ((1 - x[1]) * b - x[2] * punish) * x[0]

    function_1 = x[0] * (1 - x[0]) * (piC - piD)
    function_2 = xi * x[1] * (1 - x[1]) * (piD - piC) # 考虑收益

    # function_3 = xi * x[1] * (1 - x[1]) * (1-2 * x[0]) # 考虑群体中合作者与背叛者


    return [function_1, function_2]


def plot_Time_evolution_chart(x,t):
    Collaborator_ratio = [sublist[0] for sublist in x]
    Degree_of_rewards_and_punishments = [sublist[1] for sublist in x]

    plt.plot(t,Collaborator_ratio)
    plt.xlabel('t')
    plt.ylabel('pc')
    plt.title("Collaborator_ratio_b=2")
    plt.show()

    plt.plot(t,Degree_of_rewards_and_punishments)
    plt.xlabel('t')
    plt.ylabel('degree')
    plt.title("Degree_of_rewards_and_punishments_b=2")
    plt.show()


def plot_variogram(x,b):

    Collaborator_ratio = [sublist[0] for sublist in x]
    Degree_of_rewards_and_punishments = [sublist[1] for sublist in x]

    plt.plot(b,Collaborator_ratio)
    plt.xlabel('b')
    plt.ylabel('pc')
    plt.title("Collaborator_ratio")
    plt.show()

    plt.plot(b,Degree_of_rewards_and_punishments)
    plt.xlabel('b')
    plt.ylabel('degree')
    plt.title("Degree_of_rewards_and_punishments")
    plt.show()

    # plt.suptitle("Parameter settings {}".format(remark))
    # plt.savefig(r'C:/Users/NewNLPer/Desktop/za/exp_figure/{}.png'.format(remark))
    # plt.show()


def linespace(start,end,interval):

    float_lens = len(str(interval).split(".")[-1])
    save_list = []
    while start <= end:
        save_list.append(start)
        start += interval
        start = round(start,float_lens)
    if save_list[-1] != end:
        save_list.append(end)
    return save_list

def get_round(list):

    return [round(item,3) for item in list]

if __name__=="__main__":
    initial_x = [0.5, 0.1]
    t = np.linspace(0, 20000, 20000)
    punish = 1
    xi = 0.01


    # # 1. 固定背叛诱惑b的时间演化图
    # b = 2
    # result = odeint(Cooperation_proportion_derivatives, initial_x, t, args=(punish, b, xi))
    # plot_Time_evolution_chart(result,t)
    # print(result[-1])

   # 2. 背叛诱惑b变量的演化图
    result_finally=[]
    line_space_b=linespace(1,2,0.0001)
    for b in tqdm(line_space_b):
        result = odeint(Cooperation_proportion_derivatives, initial_x, t, args=(punish, b, xi))
        result_finally.append(get_round(result[-1].tolist()))
    plot_variogram(result_finally, line_space_b)








