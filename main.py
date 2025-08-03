from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
import aiohttp
import json
import re

@register("chat-cnb", "valetzx", "基于 CNB 知识库的对话插件", "1.1.0")
class CnbPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.token = (
            config.get("token")
            or (context.get("token") if hasattr(context, "get") else None)
        )
        self.repo = (
            config.get("repo")
            or (context.get("repo") if hasattr(context, "get") else None)
            or "cnb/docs"
        )
        self.think = (
            config.get("think")
            or (context.get("think") if hasattr(context, "get") else None)
            or False
        )

    async def initialize(self):
        """插件初始化"""

    @filter.command("cnb")
    async def cnb(self, event: AstrMessageEvent):
        """查询 CNB 知识库并生成回答"""
        message = event.message_str.strip()
        if not message:
            yield event.plain_result("请在指令后提供问题，例如 `/cnb 你的问题`")
            return

        # 思考模式开关
        if message.lower().startswith("think"):
            parts = message.split(maxsplit=1)
            if len(parts) > 1 and parts[1].lower() == "on":
                self.think = True
                yield event.plain_result("已开启思考模式")
            elif len(parts) > 1 and parts[1].lower() == "off":
                self.think = False
                yield event.plain_result("已关闭思考模式")
            else:
                yield event.plain_result("用法: `/cnb think on|off`")
            return

        # 允许用户在指令中指定知识库，例如 `/cnb user/repo 你的问题`
        parts = message.split(maxsplit=1)
        repo = self.repo
        if "/" in parts[0]:
            repo = parts[0]
            if len(parts) < 2 or not parts[1].strip():
                yield event.plain_result("请在指令后提供问题，例如 `/cnb 知识库 你的问题`")
                return
            question = parts[1].strip()
        else:
            question = message

        if not self.token:
            yield event.plain_result("插件未配置 token")
            return
        if not repo:
            yield event.plain_result("插件未配置 repo")
            return

        try:
            async with aiohttp.ClientSession() as session:
                query_url = f"https://api.cnb.cool/{repo}/-/knowledge/base/query"
                headers = {
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                    "accept": "application/json",
                }
                async with session.post(query_url, headers=headers, json={"query": question}) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        yield event.plain_result(f"查询失败: {resp.status} {text}")
                        return
                    data = await resp.json()

            if not isinstance(data, list):
                yield event.plain_result("知识库返回格式错误")
                return

            yield event.plain_result("查询成功，正在回答")

            knowledge_content = "\n\n".join(item.get("chunk", "") for item in data)
            rag_prompt = (
                "基于以下知识库内容回答用户问题：\n"
                "知识库内容：\n"
                f"{knowledge_content}\n"
                f"用户问题：{question}\n"
                "请先在 <think> 标签中给出思考过程，然后在 <answer> 标签中给出最终回答。如果知识库中没有相关信息，请明确说明。\n"
            )

            async with aiohttp.ClientSession() as session:
                chat_url = f"https://api.cnb.cool/{repo}/-/ai/chat/completions"
                payload = {
                    "messages": [{"role": "user", "content": rag_prompt}],
                    "model": "gpt-3.5-turbo",
                    "stream": True,
                }
                headers = {
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                    "accept": "application/json",
                }
                async with session.post(chat_url, headers=headers, json=payload) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        yield event.plain_result(f"AI 请求失败: {resp.status} {text}")
                        return
                    answer = ""
                    async for line in resp.content:
                        line = line.decode("utf-8").strip()
                        if not line:
                            continue
                        if line.startswith("data:"):
                            line = line[5:].strip()
                        if line == "[DONE]":
                            break
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        delta = (
                            chunk.get("choices", [{}])[0]
                            .get("delta", {})
                            .get("content")
                        )
                        if delta:
                            answer += delta

            refs = [
                item.get("metadata", {}).get("permalink")
                for item in data
                if item.get("metadata", {}).get("permalink")
            ]
            think_content = ""
            answer_match = re.search(r"<answer>(.*?)</answer>", answer, re.DOTALL)
            if answer_match:
                answer_content = answer_match.group(1).strip()
            else:
                answer_content = answer.strip()
            think_match = re.search(r"<think>(.*?)</think>", answer, re.DOTALL)
            if think_match:
                think_content = think_match.group(1).strip()
            if refs:
                answer_content += "\n\n参考资料:\n" + "\n".join(refs)

            if self.think:
                if think_content:
                    yield event.plain_result(f"<think>{think_content}</think>")
                yield event.plain_result(f"<answer>{answer_content}</answer>")
            else:
                yield event.plain_result(f"<answer>{answer_content}</answer>")
        except Exception as e:
            logger.exception(e)
            yield event.plain_result("处理失败")

    async def terminate(self):
        """插件销毁"""
