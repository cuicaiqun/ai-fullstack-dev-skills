# My RAG Interview Practice

秋招 **AI 应用开发岗** 复现学习台账。  
计划：[`../AI应用开发岗_秋招复现计划.md`](../AI应用开发岗_秋招复现计划.md)

## 重要说明

真实业务项目与环境 **已在 `project/code/python` 跑通**（API 常见端口 **8080**）。  
本目录优先放：

- 架构/口述/进度笔记
- 可选的最小重写练习代码（Day3+ 再扩展）

不要为了“再搭一套”浪费时间。

## Day 1 你现在就做

1. 打开 [`notes/day01_checklist.md`](notes/day01_checklist.md) 按清单执行  
2. 阅读 [`notes/architecture.md`](notes/architecture.md)  
3. 用 [`notes/day01_oral.md`](notes/day01_oral.md) 练 5 分钟口述  
4. 勾选 [`notes/progress.md`](notes/progress.md)

### 真实服务常用入口

```bash
curl -s http://127.0.0.1:8080/api/health | python -m json.tool
# Swagger: http://127.0.0.1:8080/docs
# 启动方式见: ../CLAUDE.md
```

## 目录

```text
my_rag_interview/
├── README.md
├── app/                    # 可选：最小重写骨架（非主运行栈）
├── notes/
│   ├── architecture.md     # 架构地图 + 5 分钟稿
│   ├── day01_oral.md       # 快问快答
│   ├── day01_checklist.md  # 今日实操清单
│   └── progress.md
├── data/
└── tests/
```
