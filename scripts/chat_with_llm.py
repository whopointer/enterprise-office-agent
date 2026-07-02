"""直接测试 .env 中配置的大模型是否能对话。"""

from __future__ import annotations

from pathlib import Path
import argparse
import os
import sys

from dotenv import load_dotenv
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from llm.skill_router import _normalize_openai_base_url


def main() -> None:
    """命令行入口。"""
    parser = argparse.ArgumentParser(description="测试 .env 里的大模型对话")
    parser.add_argument("message", nargs="*", help="单轮消息；不传则进入交互模式")
    parser.add_argument("--model", default=None, help="覆盖 .env 中的 MODEL")
    parser.add_argument("--temperature", type=float, default=0.2)
    args = parser.parse_args()

    _load_env()
    client = _build_client()
    model = args.model or os.environ.get("MODEL") or os.environ.get("OPENAI_MODEL")
    if not model:
        raise RuntimeError("缺少 MODEL / OPENAI_MODEL")

    messages: list[dict[str, str]] = [{"role": "system", "content": "你是一个简洁、准确的中文助手。"}]
    if args.message:
        user_message = " ".join(args.message)
        print(_ask(client, model, messages, user_message, args.temperature))
        return

    print(f"model={model}")
    print("输入 exit / quit 退出。")
    while True:
        user_message = input("\n你: ").strip()
        if user_message.lower() in {"exit", "quit"}:
            break
        if not user_message:
            continue
        answer = _ask(client, model, messages, user_message, args.temperature)
        print(f"模型: {answer}")


def _load_env() -> None:
    """从当前目录或父目录加载 .env。"""
    for base in (Path.cwd(), *Path.cwd().parents):
        env_path = base / ".env"
        if env_path.is_file():
            load_dotenv(dotenv_path=env_path)
            return
    load_dotenv(dotenv_path=Path(".env"))


def _build_client() -> OpenAI:
    """构造 OpenAI-compatible 客户端。"""
    api_key = os.environ.get("API_KEY") or os.environ.get("OPENAI_API_KEY")
    base_url = os.environ.get("BASE_URL") or os.environ.get("OPENAI_BASE_URL")
    if not api_key:
        raise RuntimeError("缺少 API_KEY / OPENAI_API_KEY")
    if not base_url:
        raise RuntimeError("缺少 BASE_URL / OPENAI_BASE_URL")
    return OpenAI(api_key=api_key, base_url=_normalize_openai_base_url(base_url))


def _ask(
    client: OpenAI,
    model: str,
    messages: list[dict[str, str]],
    user_message: str,
    temperature: float,
) -> str:
    """发送一轮消息，并把回复追加到上下文。"""
    messages.append({"role": "user", "content": user_message})
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
    )
    answer = response.choices[0].message.content or ""
    messages.append({"role": "assistant", "content": answer})
    return answer


if __name__ == "__main__":
    main()
