from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import aiohttp

@register("chat-cnb", "OpenAI", "基于 CNB 知识库的对话插件", "1.0.0")
class CnbPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.token = self.context.get("token") if hasattr(self.context, "get") else None
        self.repo = (
            self.context.get("repo") if hasattr(self.context, "get") else None
        ) or "cnb/docs"

    async def initialize(self):
        """插件初始化"""

    @filter.command("cnb")
    async def cnb(self, event: AstrMessageEvent):
        """查询 CNB 知识库并生成回答"""
        question = event.message_str.strip()
        if not question:
            yield event.plain_result("请在指令后提供问题，例如 `/cnb 你的问题`")
            return

        if not self.token:
            yield event.plain_result("插件未配置 token")
            return
        if not self.repo:
            yield event.plain_result("插件未配置 repo")
            return

        try:
            async with aiohttp.ClientSession() as session:
                query_url = f"https://api.cnb.cool/{self.repo}/-/knowledge/base/query"
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

            knowledge_content = "\n\n".join(item.get("chunk", "") for item in data)
            rag_prompt = (
                "基于以下知识库内容回答用户问题：\n"
                "知识库内容：\n"
                f"{knowledge_content}\n"
                f"用户问题：{question}\n"
                "请基于上述知识库内容，准确、详细地回答用户的问题。如果知识库中没有相关信息，请明确说明。\n"
                "在回答的最后，请添加一个\"参考资料\"部分，列出回答中引用的相关资料链接。\n"
            )

            async with aiohttp.ClientSession() as session:
                chat_url = f"https://api.cnb.cool/{self.repo}/-/ai/chat/completions"
                payload = {
                    "messages": [{"role": "user", "content": rag_prompt}],
                    "model": "gpt-3.5-turbo",
                    "stream": False,
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
                    ai_data = await resp.json()

            answer = (
                ai_data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            if not answer:
                answer = str(ai_data)

            refs = [
                item.get("metadata", {}).get("permalink")
                for item in data
                if item.get("metadata", {}).get("permalink")
            ]
            if refs:
                answer += "\n\n参考资料:\n" + "\n".join(refs)

            yield event.plain_result(answer)
        except Exception as e:
            logger.exception(e)
            yield event.plain_result("处理失败")

    async def terminate(self):
        """插件销毁"""
