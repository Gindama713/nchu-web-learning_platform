"""给演示课程补齐第一章的知识点、题库、作业与随堂测。

只写入本地演示库，不替代真实教学数据。脚本可重复执行：章节、知识点、
题目、试卷都按标题/题干复用，已有答卷和错题不会重复写。

    python scripts/seed_demo_content.py --db instance/app.db
    python scripts/seed_demo_content.py --db D:/.../run-data/app.db --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

CHAPTER_TITLE = "第一章 计算机组成概述"

KPS = [
    {
        "key": "k2",
        "title": "冯·诺依曼体系结构",
        "content": (
            "<h2>存储程序思想</h2>"
            "<p>冯·诺依曼体系结构的核心是“存储程序”：程序和数据都以二进制形式存放在同一个存储器中，"
            "计算机按地址顺序取出指令并自动执行。</p>"
            "<ul><li>采用二进制表示指令和数据</li>"
            "<li>指令和数据存放在同一存储器</li>"
            "<li>指令由操作码和地址码组成</li>"
            "<li>程序执行时按顺序取指，遇到转移指令改变执行顺序</li></ul>"
        ),
        "example": (
            "<p>加法程序与参与运算的数据都存放在主存中，CPU 通过取指周期读出指令，"
            "再在执行周期读取操作数。</p>"
        ),
        "is_foundational": 1,
    },
    {
        "key": "k3",
        "title": "程序计数器与指令执行",
        "content": (
            "<h2>程序计数器 PC</h2>"
            "<p>程序计数器（Program Counter，PC）保存下一条将要执行指令的地址。取指周期结束后，"
            "PC 通常自动加上当前指令的长度，指向下一条指令；执行转移指令时，PC 被修改为目标地址。</p>"
            "<p>一条指令的执行通常经过取指、译码、执行等阶段。</p>"
        ),
        "example": "<p>若当前指令地址为 1000H、指令长 4 字节，则取指后 PC 变为 1004H。</p>",
        "is_foundational": 1,
    },
    {
        "key": "k4",
        "title": "指令格式与寻址方式",
        "content": (
            "<h2>指令格式</h2>"
            "<p>机器指令通常由操作码和地址码组成：操作码指明做什么，地址码给出操作数或操作数地址。</p>"
            "<h2>常见寻址方式</h2>"
            "<ul><li>立即寻址：操作数直接放在指令中</li>"
            "<li>直接寻址：指令给出操作数的主存地址</li>"
            "<li>间接寻址：指令给出地址的地址</li>"
            "<li>寄存器寻址：操作数放在寄存器中</li></ul>"
        ),
        "example": "<p>指令“ADD R1, #5”中的 #5 是立即数，采用立即寻址。</p>",
        "is_foundational": 0,
    },
    {
        "key": "k5",
        "title": "运算器与 ALU",
        "content": (
            "<h2>运算器</h2>"
            "<p>运算器负责算术运算和逻辑运算，核心部件是算术逻辑单元（ALU）。"
            "运算器通常还包含累加器、通用寄存器和状态寄存器。</p>"
            "<p>在补码表示下，减法可以转换为加上负数的补码，从而用加法器完成减法。</p>"
        ),
        "example": (
            "<p>计算 7-3 时，可转换为 7+(-3) 的补码加法，ALU 输出结果 4，并置位相应状态标志。</p>"
        ),
        "is_foundational": 0,
    },
    {
        "key": "k6",
        "title": "控制器与指令周期",
        "content": (
            "<h2>控制器</h2>"
            "<p>控制器负责从存储器取出指令、译码并产生控制信号，协调运算器、存储器和输入输出设备工作。</p>"
            "<h2>指令周期</h2>"
            "<p>指令周期是执行一条指令所需的时间，通常包括取指周期、间址周期、执行周期和中断周期；"
            "每个周期又由若干机器周期和时钟周期组成。</p>"
        ),
        "example": (
            "<p>取指周期完成“PC→MAR，读存储器，MDR→IR，PC+1”；"
            "执行周期根据操作码发出相应控制信号。</p>"
        ),
        "is_foundational": 0,
    },
    {
        "key": "k7",
        "title": "存储器层次与 Cache",
        "content": (
            "<h2>存储器层次结构</h2>"
            "<p>存储系统按速度、容量和价格形成层次：寄存器—Cache—主存—辅存。"
            "越靠近 CPU 速度越快、容量越小、单位价格越高。</p>"
            "<h2>Cache</h2>"
            "<p>Cache 是位于 CPU 与主存之间的高速小容量存储器，保存主存中近期可能被访问的数据副本，"
            "用来缓解 CPU 与主存之间的速度差距。</p>"
            "<p>平均访问时间 = 命中率 × 命中时间 + (1-命中率) × 缺失代价。</p>"
        ),
        "example": (
            "<p>命中率 95%、命中时间 1 ns、缺失代价 100 ns 时，"
            "平均访问时间 = 0.95×1 + 0.05×100 = 5.95 ns。</p>"
        ),
        "is_foundational": 0,
    },
    {
        "key": "k8",
        "title": "总线与 I/O 接口",
        "content": (
            "<h2>总线</h2>"
            "<p>总线是多个部件共享的信息传输通道。按传输信息可分为数据总线、地址总线和控制总线："
            "数据总线传送数据，地址总线传送地址，控制总线传送控制信号。</p>"
            "<h2>I/O 接口</h2>"
            "<p>I/O 接口连接外设与系统总线，完成数据缓冲、格式转换、状态检测和中断请求等功能。</p>"
        ),
        "example": (
            "<p>CPU 读主存时，地址总线送出地址，控制总线发出读信号，数据总线把读出的数据送回 CPU。</p>"
        ),
        "is_foundational": 0,
    },
    {
        "key": "k9",
        "title": "数据表示与补码",
        "content": (
            "<h2>机器数</h2>"
            "<p>计算机中的有符号整数通常用补码表示。正数的补码与原码相同；"
            "负数的补码等于其绝对值的二进制按位取反再加 1。</p>"
            "<p>n 位补码的表示范围是 -2^(n-1) 到 2^(n-1)-1。补码的 0 只有一种表示，减法可转换为加法。</p>"
        ),
        "example": "<p>8 位补码中，-1 = 11111111，-128 = 10000000，表示范围为 -128～127。</p>",
        "is_foundational": 0,
    },
    {
        "key": "k10",
        "title": "CPU 性能指标",
        "content": (
            "<h2>性能公式</h2>"
            "<p>CPU 执行时间 = 指令条数 × CPI × 时钟周期 = 指令条数 × CPI / 主频。</p>"
            "<p>CPI 表示每条指令平均所需的时钟周期数；MIPS 表示每秒执行多少百万条指令："
            "MIPS = 主频(MHz) / CPI。</p>"
            "<p>主频、CPI 和指令条数共同决定程序执行时间，不能只看主频判断性能。</p>"
        ),
        "example": "<p>主频 2 GHz、CPI=4 时，MIPS = 2000/4 = 500。</p>",
        "is_foundational": 0,
    },
]

QUESTIONS = [
    {
        "key": "q4",
        "type": "single",
        "stem": "冯·诺依曼体系结构的核心思想是？",
        "options": [("A", "存储程序"), ("B", "并行计算"), ("C", "流水线执行"), ("D", "虚拟存储")],
        "answer": "A",
        "explanation": "存储程序思想把程序和数据都放入存储器，由计算机自动按顺序取指执行。",
        "difficulty": "easy",
        "knowledge": ["k2"],
    },
    {
        "key": "q5",
        "type": "multiple",
        "stem": "冯·诺依曼计算机通常由哪些部件组成？",
        "options": [
            ("A", "运算器"),
            ("B", "控制器"),
            ("C", "存储器"),
            ("D", "输入设备"),
            ("E", "输出设备"),
        ],
        "answer": ["A", "B", "C", "D", "E"],
        "explanation": "冯·诺依曼计算机由运算器、控制器、存储器、输入设备和输出设备五大部件组成。",
        "difficulty": "easy",
        "knowledge": ["k2"],
    },
    {
        "key": "q6",
        "type": "boolean",
        "stem": "冯·诺依曼计算机中，指令和数据都以二进制形式存放在存储器中。",
        "options": [],
        "answer": True,
        "explanation": "存储程序思想要求指令和数据统一以二进制形式存放在同一存储器中。",
        "difficulty": "easy",
        "knowledge": ["k2"],
    },
    {
        "key": "q7",
        "type": "short",
        "stem": "简述冯·诺依曼体系结构的核心思想及主要组成部分。",
        "options": [],
        "answer": "核心思想是存储程序：程序和数据以二进制形式存放在同一存储器中，计算机自动按顺序取指执行。主要组成部分包括运算器、控制器、存储器、输入设备和输出设备。",
        "explanation": "评分要点：存储程序、指令和数据同存、五大部件。",
        "difficulty": "medium",
        "knowledge": ["k2"],
        "practice": False,
    },
    {
        "key": "q8",
        "type": "single",
        "stem": "程序计数器 PC 中存放的是？",
        "options": [
            ("A", "当前指令的操作码"),
            ("B", "下一条将要执行指令的地址"),
            ("C", "当前指令的执行结果"),
            ("D", "栈顶地址"),
        ],
        "answer": "B",
        "explanation": "PC 保存下一条将要执行指令的地址，取指后通常自动更新。",
        "difficulty": "easy",
        "knowledge": ["k3"],
    },
    {
        "key": "q9",
        "type": "single",
        "stem": "取指周期结束后，若没有发生转移，PC 通常会？",
        "options": [("A", "保持不变"), ("B", "加上当前指令长度"), ("C", "清零"), ("D", "减 1")],
        "answer": "B",
        "explanation": "取指后 PC 自动加上当前指令长度，指向下一条指令。",
        "difficulty": "easy",
        "knowledge": ["k3"],
    },
    {
        "key": "q10",
        "type": "multiple",
        "stem": "关于程序计数器 PC，下列说法正确的有？",
        "options": [
            ("A", "保存下一条指令地址"),
            ("B", "可由转移指令修改"),
            ("C", "取指后通常自动更新"),
            ("D", "存放当前指令的操作数"),
        ],
        "answer": ["A", "B", "C"],
        "explanation": "PC 保存地址而不是操作数；转移指令会改写 PC。",
        "difficulty": "medium",
        "knowledge": ["k3"],
    },
    {
        "key": "q11",
        "type": "short",
        "stem": "简述一条指令从取出到执行的基本过程。",
        "options": [],
        "answer": "控制器先按 PC 给出的地址从存储器取指令送入指令寄存器，PC 自动更新；然后对指令译码，产生控制信号，从寄存器或存储器取出操作数，由运算器执行运算，最后写回结果。",
        "explanation": "评分要点：取指、译码、取操作数、执行、写回。",
        "difficulty": "medium",
        "knowledge": ["k3"],
        "practice": False,
    },
    {
        "key": "q12",
        "type": "single",
        "stem": "指令中给出操作数地址的方式称为？",
        "options": [("A", "寻址方式"), ("B", "指令周期"), ("C", "中断方式"), ("D", "总线周期")],
        "answer": "A",
        "explanation": "寻址方式描述指令如何给出操作数或操作数地址。",
        "difficulty": "easy",
        "knowledge": ["k4"],
    },
    {
        "key": "q13",
        "type": "single",
        "stem": "立即寻址方式中，操作数位于？",
        "options": [("A", "指令中"), ("B", "主存单元"), ("C", "寄存器"), ("D", "I/O 端口")],
        "answer": "A",
        "explanation": "立即寻址把操作数直接编码在指令中。",
        "difficulty": "easy",
        "knowledge": ["k4"],
    },
    {
        "key": "q14",
        "type": "multiple",
        "stem": "下列属于常见寻址方式的有？",
        "options": [
            ("A", "立即寻址"),
            ("B", "直接寻址"),
            ("C", "间接寻址"),
            ("D", "寄存器寻址"),
        ],
        "answer": ["A", "B", "C", "D"],
        "explanation": "四种都是计算机中常见的寻址方式。",
        "difficulty": "easy",
        "knowledge": ["k4"],
    },
    {
        "key": "q15",
        "type": "single",
        "stem": "运算器的核心部件是？",
        "options": [
            ("A", "算术逻辑单元 ALU"),
            ("B", "程序计数器"),
            ("C", "指令寄存器"),
            ("D", "地址译码器"),
        ],
        "answer": "A",
        "explanation": "ALU 完成算术和逻辑运算，是运算器的核心。",
        "difficulty": "easy",
        "knowledge": ["k5"],
    },
    {
        "key": "q16",
        "type": "multiple",
        "stem": "下列属于 ALU 常见运算的有？",
        "options": [("A", "加法"), ("B", "减法"), ("C", "逻辑与"), ("D", "逻辑或")],
        "answer": ["A", "B", "C", "D"],
        "explanation": "ALU 既做算术运算，也做逻辑运算。",
        "difficulty": "easy",
        "knowledge": ["k5"],
    },
    {
        "key": "q17",
        "type": "single",
        "stem": "在补码表示下，减法运算通常可以转换为？",
        "options": [
            ("A", "加上负数的补码"),
            ("B", "乘以 2"),
            ("C", "逻辑右移"),
            ("D", "按位取反"),
        ],
        "answer": "A",
        "explanation": "补码把减法转换为加法，使同一套加法器可以完成加减运算。",
        "difficulty": "medium",
        "knowledge": ["k5", "k9"],
    },
    {
        "key": "q18",
        "type": "boolean",
        "stem": "两个正数相加时，结果一定仍为正数。",
        "options": [],
        "answer": False,
        "explanation": "两个正数相加可能超出表示范围而发生溢出，结果的符号位可能改变。",
        "difficulty": "medium",
        "knowledge": ["k5", "k9"],
    },
    {
        "key": "q19",
        "type": "single",
        "stem": "指令周期通常包括？",
        "options": [
            ("A", "取指、间址、执行、中断等阶段"),
            ("B", "只需要执行阶段"),
            ("C", "只需要取指阶段"),
            ("D", "编译、链接、运行"),
        ],
        "answer": "A",
        "explanation": "指令周期通常由取指、间址、执行和中断等阶段组成。",
        "difficulty": "easy",
        "knowledge": ["k6"],
    },
    {
        "key": "q20",
        "type": "multiple",
        "stem": "下列可能属于指令周期阶段的有？",
        "options": [("A", "取指周期"), ("B", "间址周期"), ("C", "执行周期"), ("D", "中断周期")],
        "answer": ["A", "B", "C", "D"],
        "explanation": "四个阶段都可能出现在指令周期中，具体取决于指令和系统。",
        "difficulty": "medium",
        "knowledge": ["k6"],
    },
    {
        "key": "q21",
        "type": "single",
        "stem": "控制器的主要功能是？",
        "options": [
            ("A", "产生控制信号并协调各部件工作"),
            ("B", "长期保存程序"),
            ("C", "显示运算结果"),
            ("D", "连接外部网络"),
        ],
        "answer": "A",
        "explanation": "控制器负责取指、译码并产生控制信号，协调各部件。",
        "difficulty": "easy",
        "knowledge": ["k6"],
    },
    {
        "key": "q22",
        "type": "single",
        "stem": "Cache 的主要作用是？",
        "options": [
            ("A", "缓解 CPU 与主存之间的速度差距"),
            ("B", "扩大主存容量"),
            ("C", "替代外存"),
            ("D", "提高显示分辨率"),
        ],
        "answer": "A",
        "explanation": "Cache 保存主存数据副本，减少 CPU 等待主存的时间。",
        "difficulty": "easy",
        "knowledge": ["k7"],
    },
    {
        "key": "q23",
        "type": "single",
        "stem": "下列存储器中，访问速度通常最快的是？",
        "options": [("A", "寄存器"), ("B", "Cache"), ("C", "主存"), ("D", "磁盘")],
        "answer": "A",
        "explanation": "寄存器位于 CPU 内部，速度最快；层次越往下速度越慢。",
        "difficulty": "easy",
        "knowledge": ["k7"],
    },
    {
        "key": "q24",
        "type": "multiple",
        "stem": "Cache 命中率提高，可能带来的影响有？",
        "options": [
            ("A", "平均访问时间降低"),
            ("B", "CPU 等待主存的时间减少"),
            ("C", "主存容量自动增大"),
            ("D", "磁盘容量自动增大"),
        ],
        "answer": ["A", "B"],
        "explanation": "命中率提高减少访问主存的次数，从而降低平均访问时间。",
        "difficulty": "medium",
        "knowledge": ["k7"],
    },
    {
        "key": "q25",
        "type": "boolean",
        "stem": "Cache 的容量通常比主存大。",
        "options": [],
        "answer": False,
        "explanation": "Cache 容量通常远小于主存，用来保存近期可能访问的数据副本。",
        "difficulty": "easy",
        "knowledge": ["k7"],
    },
    {
        "key": "q26",
        "type": "numeric",
        "stem": "某 Cache 命中率 95%，命中时间 1 ns，缺失代价 100 ns，平均访问时间是多少 ns？",
        "options": [],
        "answer": 5.95,
        "tolerance": 0.01,
        "explanation": "平均访问时间 = 0.95×1 + 0.05×100 = 5.95 ns。",
        "difficulty": "medium",
        "knowledge": ["k7"],
    },
    {
        "key": "q27",
        "type": "short",
        "stem": "简述 Cache 的作用和基本原理。",
        "options": [],
        "answer": "Cache 是位于 CPU 与主存之间的高速小容量存储器，保存主存中近期可能被访问的数据副本。CPU 访问时先查 Cache，命中则直接读取，未命中再访问主存并把数据调入 Cache，从而缓解 CPU 与主存的速度差距。",
        "explanation": "评分要点：位置、保存副本、命中/未命中、缓解速度差。",
        "difficulty": "medium",
        "knowledge": ["k7"],
        "practice": False,
    },
    {
        "key": "q28",
        "type": "single",
        "stem": "数据总线用于传输？",
        "options": [("A", "数据"), ("B", "地址"), ("C", "控制信号"), ("D", "电源")],
        "answer": "A",
        "explanation": "数据总线在部件之间传送数据。",
        "difficulty": "easy",
        "knowledge": ["k8"],
    },
    {
        "key": "q29",
        "type": "multiple",
        "stem": "总线按传输信息可分为？",
        "options": [("A", "数据总线"), ("B", "地址总线"), ("C", "控制总线"), ("D", "电源总线")],
        "answer": ["A", "B", "C"],
        "explanation": "系统总线通常分为数据总线、地址总线和控制总线。",
        "difficulty": "easy",
        "knowledge": ["k8"],
    },
    {
        "key": "q30",
        "type": "boolean",
        "stem": "总线是多个部件共享的信息传输通道。",
        "options": [],
        "answer": True,
        "explanation": "总线由多个部件共享，需要分时使用。",
        "difficulty": "easy",
        "knowledge": ["k8"],
    },
    {
        "key": "q31",
        "type": "single",
        "stem": "8 位补码 11111111 表示的十进制真值是？",
        "options": [("A", "-1"), ("B", "1"), ("C", "255"), ("D", "-128")],
        "answer": "A",
        "explanation": "11111111 按位取反加 1 得到 -1，或由 -128+127 计算得出 -1。",
        "difficulty": "medium",
        "knowledge": ["k9"],
    },
    {
        "key": "q32",
        "type": "single",
        "stem": "8 位补码能表示的整数范围是？",
        "options": [("A", "-128～127"), ("B", "0～255"), ("C", "-127～127"), ("D", "-255～255")],
        "answer": "A",
        "explanation": "n 位补码表示范围为 -2^(n-1)～2^(n-1)-1，n=8 时为 -128～127。",
        "difficulty": "medium",
        "knowledge": ["k9"],
    },
    {
        "key": "q33",
        "type": "multiple",
        "stem": "补码表示的主要优点有？",
        "options": [
            ("A", "减法可转换为加法"),
            ("B", "0 只有一种表示"),
            ("C", "可以直接表示浮点数"),
            ("D", "不需要符号位"),
        ],
        "answer": ["A", "B"],
        "explanation": "补码统一了加减法且 0 表示唯一；它仍需要符号位，也不直接表示浮点数。",
        "difficulty": "medium",
        "knowledge": ["k9"],
    },
    {
        "key": "q34",
        "type": "boolean",
        "stem": "在补码表示中，0 有 +0 和 -0 两种形式。",
        "options": [],
        "answer": False,
        "explanation": "补码的 0 只有一种表示；原码和反码才有 +0、-0 两种形式。",
        "difficulty": "medium",
        "knowledge": ["k9"],
    },
    {
        "key": "q35",
        "type": "numeric",
        "stem": "8 位补码 10000000 表示的十进制真值是多少？",
        "options": [],
        "answer": -128,
        "explanation": "10000000 是 8 位补码能表示的最小负数 -128。",
        "difficulty": "medium",
        "knowledge": ["k9"],
    },
    {
        "key": "q36",
        "type": "single",
        "stem": "MIPS 的含义是？",
        "options": [
            ("A", "每秒执行百万条指令数"),
            ("B", "每条指令的时钟周期数"),
            ("C", "主频的倒数"),
            ("D", "存储器容量"),
        ],
        "answer": "A",
        "explanation": "MIPS = Million Instructions Per Second，即每秒百万条指令。",
        "difficulty": "easy",
        "knowledge": ["k10"],
    },
    {
        "key": "q37",
        "type": "numeric",
        "stem": "某 CPU 主频 1 GHz，CPI=2，执行 10^8 条指令需要多少秒？",
        "options": [],
        "answer": 0.2,
        "tolerance": 0.0001,
        "explanation": "时钟周期 = 1/1 GHz = 1 ns；总周期 = 2×10^8；时间 = 0.2 s。",
        "difficulty": "medium",
        "knowledge": ["k10"],
    },
    {
        "key": "q38",
        "type": "numeric",
        "stem": "某 CPU 主频 2 GHz，CPI=4，MIPS 是多少？",
        "options": [],
        "answer": 500,
        "explanation": "MIPS = 主频(MHz)/CPI = 2000/4 = 500。",
        "difficulty": "medium",
        "knowledge": ["k10"],
    },
    {
        "key": "q39",
        "type": "numeric",
        "stem": "某程序共 1000 条指令，平均 CPI=3，主频 1.5 GHz，执行时间是多少微秒？",
        "options": [],
        "answer": 2,
        "tolerance": 0.01,
        "explanation": "总周期 = 3000，时钟周期 = 1/1.5 GHz，时间 = 2×10^-6 s = 2 微秒。",
        "difficulty": "hard",
        "knowledge": ["k10"],
    },
    {
        "key": "q40",
        "type": "boolean",
        "stem": "主频越高，CPU 的实际性能一定越高。",
        "options": [],
        "answer": False,
        "explanation": "性能还取决于 CPI、指令条数等，不能只看主频。",
        "difficulty": "easy",
        "knowledge": ["k10"],
    },
    {
        "key": "q41",
        "type": "single",
        "stem": "计算机硬件系统中，负责长期存储程序和数据的是？",
        "options": [("A", "存储器"), ("B", "运算器"), ("C", "控制器"), ("D", "输入设备")],
        "answer": "A",
        "explanation": "存储器用于存放程序和数据，是计算机的记忆部件。",
        "difficulty": "easy",
        "knowledge": ["k1"],
    },
]

PAPERS = [
    {
        "key": "homework",
        "title": "作业一：计算机系统与数据表示",
        "kind": "homework",
        "items": [
            ("q41", 6),
            ("q4", 6),
            ("q5", 6),
            ("q7", 22),
            ("q8", 6),
            ("q9", 6),
            ("q10", 6),
            ("q12", 6),
            ("q13", 6),
            ("q15", 6),
            ("q16", 6),
            ("q19", 6),
            ("q22", 6),
            ("q25", 6),
        ],
        "start": timedelta(days=-10),
        "end": timedelta(days=8),
        "review": timedelta(days=9),
        "students": 100,
    },
    {
        "key": "quiz-cpu",
        "title": "随堂测一：指令与 CPU",
        "kind": "quiz",
        "items": [
            ("q8", 10),
            ("q9", 10),
            ("q10", 10),
            ("q12", 10),
            ("q13", 10),
            ("q14", 10),
            ("q15", 10),
            ("q16", 10),
            ("q17", 10),
            ("q19", 10),
        ],
        "start": timedelta(days=-3),
        "end": timedelta(days=-2),
        "review": timedelta(days=-2, minutes=10),
        "students": 120,
    },
    {
        "key": "quiz-memory",
        "title": "随堂测二：存储层次与性能",
        "kind": "quiz",
        "items": [
            ("q22", 12.5),
            ("q23", 12.5),
            ("q24", 12.5),
            ("q25", 12.5),
            ("q26", 12.5),
            ("q36", 12.5),
            ("q37", 12.5),
            ("q40", 12.5),
        ],
        "start": timedelta(minutes=-30),
        "end": timedelta(days=7),
        "students": 50,
    },
    {
        "key": "quiz-bus-draft",
        "title": "随堂测（草稿）：总线与 I/O",
        "kind": "quiz",
        "items": [
            ("q28", 10),
            ("q29", 15),
            ("q30", 20),
            ("q31", 15),
            ("q32", 20),
            ("q34", 20),
        ],
        "students": 0,
    },
]

QA_QUESTIONS = [
    "程序计数器 PC 有什么作用？",
    "Cache 的作用是什么？",
    "补码怎么表示负数？",
]


class Rollback(Exception):
    pass


def iso(value):
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="给演示课程补齐第一章内容")
    parser.add_argument("--db", default="instance/app.db", help="数据库路径")
    parser.add_argument("--course-id", type=int, help="课程 ID；默认取 teacher 名下第一门课程")
    parser.add_argument("--dry-run", action="store_true", help="只演练并在结束时回滚")
    return parser.parse_args(argv)


def resolve_course(db, course_id):
    if course_id is not None:
        row = db.execute("SELECT * FROM course WHERE id=?", (course_id,)).fetchone()
    else:
        row = db.execute(
            "SELECT c.* FROM course c JOIN user u ON u.id=c.teacher_id "
            "WHERE u.student_no='teacher' ORDER BY c.id LIMIT 1"
        ).fetchone()
        if row is None:
            row = db.execute("SELECT * FROM course ORDER BY id LIMIT 1").fetchone()
    if row is None:
        raise SystemExit("数据库里没有可用课程，请先运行 scripts/seed_teacher_course.py")
    return dict(row)


def ensure_chapter(db, course_id, title):
    row = db.execute("SELECT * FROM chapter WHERE course_id=? AND title=?", (course_id, title)).fetchone()
    if row is not None:
        return row["id"], False
    position = db.execute(
        "SELECT coalesce(max(position),0)+1 FROM chapter WHERE course_id=?", (course_id,)
    ).fetchone()[0]
    chapter_id = db.execute(
        "INSERT INTO chapter(course_id,title,position) VALUES(?,?,?)",
        (course_id, title, position),
    ).lastrowid
    return chapter_id, True


def ensure_kp(db, chapter_id, spec):
    row = db.execute(
        "SELECT * FROM knowledge_point WHERE chapter_id=? AND title=?", (chapter_id, spec["title"])
    ).fetchone()
    if row is not None:
        return row["id"], False
    kp_id = db.execute(
        "INSERT INTO knowledge_point(chapter_id,title,content,example,published,is_foundational) "
        "VALUES(?,?,?,?,1,?)",
        (chapter_id, spec["title"], spec["content"], spec["example"], spec["is_foundational"]),
    ).lastrowid
    return kp_id, True


def ensure_question(db, course_id, spec, kp_ids):
    row = db.execute(
        "SELECT v.id AS version_id,v.question_id AS question_id FROM question_version v "
        "JOIN question q ON q.id=v.question_id WHERE q.course_id=? AND v.stem=? "
        "ORDER BY v.version DESC LIMIT 1",
        (course_id, spec["stem"]),
    ).fetchone()
    if row is not None:
        return row["question_id"], row["version_id"], False
    from backend.models import question as question_model

    values = {
        "type": spec["type"],
        "stem": spec["stem"],
        "options": [{"key": key, "text": text} for key, text in spec["options"]],
        "answer": spec["answer"],
        "explanation": spec.get("explanation", ""),
        "difficulty": spec["difficulty"],
        "tolerance": spec.get("tolerance", 0),
        "knowledge_ids": [kp_ids[key] for key in spec["knowledge"]],
        "practice_available": spec.get("practice", True),
    }
    saved = question_model.save_version(db, course_id, values)
    return saved["id"], saved["version_id"], True


def ensure_paper(db, course_id, spec, qmap, now):
    from backend.models import paper as paper_model
    from backend.models import quiz as quiz_model

    row = db.execute(
        "SELECT * FROM paper WHERE course_id=? AND title=?", (course_id, spec["title"])
    ).fetchone()
    created = False
    if row is None:
        items = [
            {"question_version_id": qmap[key]["version_id"], "points": points}
            for key, points in spec["items"]
        ]
        paper_id = paper_model.create(
            db,
            course_id,
            {
                "title": spec["title"],
                "kind": spec["kind"],
                "confidential": False,
                "items": items,
            },
        )
        row = paper_model.find(db, paper_id)
        created = True
    published = False
    if row["status"] == "draft" and "start" in spec:
        start_at = iso(now + spec["start"])
        end_at = iso(now + spec["end"])
        if spec["kind"] == "quiz":
            paper_model.publish(db, row, {"start_at": start_at, "end_at": end_at}, quiz=True)
        else:
            review_at = iso(now + spec["review"])
            paper_model.publish(
                db,
                row,
                {"start_at": start_at, "end_at": end_at, "review_at": review_at},
            )
        row = paper_model.find(db, row["id"])
        published = True
    reviewed = False
    if (
        row["kind"] == "quiz"
        and row["status"] == "published"
        and "review" in spec
        and row["review_at"] is None
        and now >= datetime.fromisoformat(row["end_at"])
    ):
        quiz_model.review(db, row, iso(now + spec["review"]))
        row = paper_model.find(db, row["id"])
        reviewed = True
    return row, created, published, reviewed


def student_rows(db, limit):
    return db.execute(
        "SELECT id,student_no,name FROM user WHERE role='student' AND active=1 "
        "AND student_no<>'24200000' ORDER BY id LIMIT ?",
        (limit,),
    ).fetchall()


def choose_at(row, index, total, now):
    start = datetime.fromisoformat(row["start_at"])
    end = datetime.fromisoformat(row["end_at"])
    lower = start + timedelta(minutes=1)
    upper = min(end, now) - timedelta(minutes=1)
    if upper <= lower:
        return iso(lower)
    return iso(lower + (upper - lower) * (index + 1) / (total + 1))


def correct_value(item):
    return json.loads(item["answer_json"])


def wrong_value(item, student_index, item_index):
    kind = item["type"]
    expected = correct_value(item)
    if kind == "single":
        keys = [option["key"] for option in json.loads(item["options_json"])]
        return next(key for key in keys if key != expected)
    if kind == "multiple":
        keys = [option["key"] for option in json.loads(item["options_json"])]
        if len(expected) > 1:
            return expected[:-1]
        return next(key for key in keys if key not in expected)
    if kind == "boolean":
        return not expected
    if kind == "numeric":
        delta = 10 if abs(expected) >= 1 else 0.5
        return expected + delta
    return f"学生 {student_index + 1} 的回答：{item['stem'][:20]}"


def should_be_correct(paper_key, student_index, item_index):
    digest = hashlib.sha256(f"{paper_key}:{student_index}:{item_index}".encode()).hexdigest()
    ability = 55 + (student_index * 7) % 40
    return int(digest[:8], 16) % 100 < ability


def answer_for(item, paper_key, student_index, item_index):
    if item["type"] != "short" and (student_index * 7 + item_index * 3) % 23 == 0:
        return None
    if item["type"] == "short":
        return f"要点包括存储程序、指令与数据同存、控制器按地址取指并执行。学生 {student_index + 1} 作答。"
    if should_be_correct(paper_key, student_index, item_index):
        return correct_value(item)
    return wrong_value(item, student_index, item_index)


def seed_attempts(db, paper_row, students, count, paper_key, teacher_id, now):
    from backend.models import attempt as attempt_model

    items = attempt_model.items(db, paper_row["id"])
    if not items or count <= 0:
        return 0, 0
    short_items = [item for item in items if item["type"] == "short"]
    created = 0
    graded_short = 0
    for student_index, student in enumerate(students[:count]):
        exists = db.execute(
            "SELECT 1 FROM attempt WHERE paper_id=? AND student_id=?",
            (paper_row["id"], student["id"]),
        ).fetchone()
        if exists is not None:
            continue
        participant = db.execute(
            "SELECT 1 FROM paper_participant WHERE paper_id=? AND student_id=?",
            (paper_row["id"], student["id"]),
        ).fetchone()
        if participant is None:
            continue
        answers = [
            {
                "question_version_id": item["id"],
                "value": answer_for(item, paper_key, student_index, item_index),
            }
            for item_index, item in enumerate(items)
        ]
        attempt_id = attempt_model.submit(
            db,
            paper_row,
            student["id"],
            items,
            answers,
            choose_at(paper_row, student_index, count, now),
        )
        created += 1
        if short_items and student_index % 15 != 13:
            grades = []
            for short_index, item in enumerate(short_items):
                max_score = item["points_hundredths"] / 100
                factor = 0.55 + ((student_index + short_index) % 5) * 0.1
                score = round(max_score * factor, 2)
                grades.append(
                    {
                        "question_version_id": item["id"],
                        "score": score,
                        "comment": "要点基本完整，注意补充指令执行阶段。" if score < max_score * 0.8 else "要点完整。",
                    }
                )
            attempt_model.manual_scores(
                db,
                attempt_model.find(db, attempt_id),
                {"revision": 0, "items": grades},
                teacher_id,
            )
            graded_short += 1
    return created, graded_short


def seed_practice(db, course_id, students, now):
    from backend.models import practice as practice_model
    from backend.models import question as question_model

    created = 0
    for student_index, student in enumerate(students[:5]):
        tried = db.execute(
            "SELECT 1 FROM practice_attempt WHERE student_id=? LIMIT 1", (student["id"],)
        ).fetchone()
        if tried is not None:
            continue
        wrongs = db.execute(
            "SELECT w.question_id FROM wrong_question w JOIN question q ON q.id=w.question_id "
            "WHERE w.student_id=? AND w.resolved=0 AND q.course_id=? ORDER BY w.id LIMIT 2",
            (student["id"], course_id),
        ).fetchall()
        for wrong_index, row in enumerate(wrongs):
            question_row = question_model.latest(db, row["question_id"])
            if question_row["type"] == "short" or not question_row["practice_available"]:
                continue
            exists = db.execute(
                "SELECT 1 FROM practice_attempt WHERE student_id=? AND question_version_id=?",
                (student["id"], question_row["id"]),
            ).fetchone()
            if exists is not None:
                continue
            at = iso(now - timedelta(hours=student_index + wrong_index + 1))
            correct = correct_value(question_row)
            if student_index < 3:
                practice_model.submit(db, question_row, student["id"], correct, at)
                created += 1
            else:
                practice_model.submit(
                    db,
                    question_row,
                    student["id"],
                    wrong_value(question_row, student_index, wrong_index),
                    at,
                )
                practice_model.submit(db, question_row, student["id"], correct, iso(now - timedelta(minutes=30)))
                created += 2
    return created


def seed_progress(db, students, kp_ids, now):
    progress = 0
    bookmarks = 0
    for student_index, student in enumerate(students[:8]):
        count = 3 + student_index % 4
        for offset, kp_id in enumerate(kp_ids[:count]):
            completed_at = iso(now - timedelta(days=student_index + offset))
            cursor = db.execute(
                "INSERT OR IGNORE INTO learning_progress(user_id,knowledge_id,completed,completed_at) "
                "VALUES(?,?,1,?)",
                (student["id"], kp_id, completed_at),
            )
            progress += cursor.rowcount
    for student in students[:3]:
        for kp_id in kp_ids[:3]:
            cursor = db.execute(
                "INSERT OR IGNORE INTO bookmark(user_id,knowledge_id) VALUES(?,?)",
                (student["id"], kp_id),
            )
            bookmarks += cursor.rowcount
    return progress, bookmarks


def main(argv=None):
    args = parse_args(argv)
    path = Path(args.db).resolve()
    if not path.exists():
        print(f"数据库不存在：{path}", file=sys.stderr)
        return 2
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from backend.app import create_app
    from backend.shared.db import get_db, write

    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "seed-demo-content-secret-key-000000",
            "DATABASE_PATH": str(path),
            "APP_ORIGIN": "http://127.0.0.1:5173",
            "UPLOAD_ROOT": str(path.parent / "uploads"),
        }
    )
    now = datetime.now(UTC)
    summary = {}
    try:
        with app.app_context(), write() as db:
                course = resolve_course(db, args.course_id)
                course_id = course["id"]
                teacher_id = course["teacher_id"]
                chapter_id, chapter_created = ensure_chapter(db, course_id, CHAPTER_TITLE)
                kp_ids = {}
                kps_created = 0
                for spec in KPS:
                    kp_ids[spec["key"]], created = ensure_kp(db, chapter_id, spec)
                    kps_created += int(created)
                if "k1" not in kp_ids:
                    row = db.execute(
                        "SELECT id FROM knowledge_point WHERE chapter_id=? AND title=?",
                        (chapter_id, "计算机系统的组成"),
                    ).fetchone()
                    if row is None:
                        raise SystemExit("缺少基础知识点“计算机系统的组成”")
                    kp_ids["k1"] = row["id"]
                qmap = {}
                questions_created = 0
                for spec in QUESTIONS:
                    question_id, version_id, created = ensure_question(db, course_id, spec, kp_ids)
                    qmap[spec["key"]] = {
                        "question_id": question_id,
                        "version_id": version_id,
                    }
                    questions_created += int(created)
                students = student_rows(db, 120)
                paper_rows = {}
                papers_created = 0
                papers_published = 0
                papers_reviewed = 0
                for spec in PAPERS:
                    row, created, published, reviewed = ensure_paper(db, course_id, spec, qmap, now)
                    paper_rows[spec["key"]] = row
                    papers_created += int(created)
                    papers_published += int(published)
                    papers_reviewed += int(reviewed)
                attempts_created = 0
                graded_short = 0
                for spec in PAPERS:
                    row = paper_rows[spec["key"]]
                    if row["status"] != "published" or "start" not in spec:
                        continue
                    created, graded = seed_attempts(
                        db, row, students, spec["students"], spec["key"], teacher_id, now
                    )
                    attempts_created += created
                    graded_short += graded
                practice_created = seed_practice(db, course_id, students, now)
                progress_created, bookmarks_created = seed_progress(
                    db, students, [kp_ids[key] for key in ("k1", "k2", "k3", "k4", "k5", "k6", "k7", "k8", "k9", "k10")], now
                )
                summary = {
                    "course_id": course_id,
                    "chapter_created": chapter_created,
                    "kps_created": kps_created,
                    "questions_created": questions_created,
                    "papers_created": papers_created,
                    "papers_published": papers_published,
                    "papers_reviewed": papers_reviewed,
                    "attempts_created": attempts_created,
                    "short_answers_graded": graded_short,
                    "practice_created": practice_created,
                    "progress_created": progress_created,
                    "bookmarks_created": bookmarks_created,
                }
                if args.dry_run:
                    raise Rollback
    except Rollback:
        print("--dry-run：已回滚，未写库")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    if "course_id" not in summary:
        print("没有找到可写入的课程", file=sys.stderr)
        return 1
    if not args.dry_run:
        from backend.models.qa import IndexCache, QAStore

        store = QAStore(str(path), None, IndexCache())
        warmed = 0
        for question in QA_QUESTIONS:
            with app.app_context():
                db = get_db()
                exists = db.execute(
                    "SELECT 1 FROM qa_query WHERE user_id=? AND course_id=? AND question=?",
                    (teacher_id, summary["course_id"], question),
                ).fetchone()
            if exists is None:
                store.ask(teacher_id, summary["course_id"], {"question": question, "top_k": 3})
                warmed += 1
        summary["qa_warmed"] = warmed
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"已写库：{path}" if not args.dry_run else "--dry-run 未写库")
    return 0


if __name__ == "__main__":
    sys.exit(main())
