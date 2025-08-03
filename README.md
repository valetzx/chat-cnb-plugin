# chat-cnb

基于 CNB 知识库的 AstrBot 插件。用户发送 `/cnb 问题` 指令后，插件会：

1. 调用 CNB 知识库查询接口获取相关内容；
2. 构造 RAG 提示词并调用 AI 对话接口生成回答；
3. 返回包含参考资料链接的回复。

## 配置

在 `_conf_schema.json` 中设置 `token`，以及可选的 `repo`（未设置时默认为 `cnb/docs`），用于访问 CNB API。

## 使用

发送 `/cnb 你的问题` 即可得到基于知识库的回答。
