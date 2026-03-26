"""
LLM API客户端模块
支持MiniMax和智谱GLM的API调用
"""
import os
import json
import time
import logging
import configparser
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from modules.utils import get_project_root


class LLMClient:
    """LLM API统一客户端"""

    # MiniMax API配置
    MINIMAX_API_URL = "https://api.minimax.chat/v1/text/chatcompletion_pro"
    MINIMAX_MODEL = "abab6.5s-chat"

    # 智谱GLM API配置
    ZHIPU_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    ZHIPU_MODEL = "glm-4"

    def __init__(self, config_file=None, logger=None):
        """
        初始化LLM客户端

        Args:
            config_file: 配置文件路径
            logger: 日志记录器
        """
        self.logger = logger or logging.getLogger(__name__)
        self.config = self._load_config(config_file)

        # MiniMax配置
        self.minimax_api_key = os.environ.get('MINIMAX_API_KEY') or \
                               self.config.get('LLM', 'minimax_api_key', fallback='')
        self.minimax_group_id = os.environ.get('MINIMAX_GROUP_ID') or \
                                self.config.get('LLM', 'minimax_group_id', fallback='')

        # 智谱GLM配置
        self.zhipu_api_key = os.environ.get('ZHIPU_API_KEY') or \
                            self.config.get('LLM', 'zhipu_api_key', fallback='')

        # 当前使用的provider
        self.current_provider = self.config.get('LLM', 'provider', fallback='minimax')

        # 并发控制
        self.batch_size = self.config.getint('LLM', 'batch_size', fallback=5)
        self.max_workers = self.config.getint('LLM', 'max_workers', fallback=5)
        self.request_delay = self.config.getfloat('LLM', 'request_delay', fallback=0.5)

        self.logger.info(f"LLM客户端初始化完成，当前provider: {self.current_provider}")

    def _load_config(self, config_file):
        """加载配置文件"""
        if config_file is None:
            config_file = os.path.join(get_project_root(), 'config', 'settings.ini')

        config = configparser.ConfigParser()
        config.read(config_file, encoding='utf-8')
        return config

    def _call_minimax(self, messages, temperature=0.3, max_tokens=2048):
        """调用MiniMax API"""
        if not self.minimax_api_key or not self.minimax_group_id:
            raise ValueError("MiniMax API Key或Group ID未配置")

        headers = {
            "Authorization": f"Bearer {self.minimax_api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.MINIMAX_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        url = f"{self.MINIMAX_API_URL}?GroupId={self.minimax_group_id}"
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()

        result = response.json()
        if 'choices' in result and len(result['choices']) > 0:
            return result['choices'][0]['message']['content']
        else:
            raise ValueError(f"MiniMax API返回格式异常: {result}")

    def _call_zhipu(self, messages, temperature=0.3, max_tokens=2048):
        """调用智谱GLM API"""
        if not self.zhipu_api_key:
            raise ValueError("智谱GLM API Key未配置")

        headers = {
            "Authorization": f"Bearer {self.zhipu_api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.ZHIPU_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        response = requests.post(self.ZHIPU_API_URL, headers=headers, json=payload, timeout=60)
        response.raise_for_status()

        result = response.json()
        if 'choices' in result and len(result['choices']) > 0:
            return result['choices'][0]['message']['content']
        else:
            raise ValueError(f"智谱GLM API返回格式异常: {result}")

    def chat(self, prompt, system_prompt=None, temperature=0.3):
        """通用聊天接口"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        if self.current_provider == 'minimax':
            return self._call_minimax(messages, temperature)
        elif self.current_provider == 'zhipu':
            return self._call_zhipu(messages, temperature)
        else:
            raise ValueError(f"不支持的LLM provider: {self.current_provider}")

    def batch_chat(self, prompts, system_prompt=None, temperature=0.3):
        """批量并发调用LLM"""
        results = [None] * len(prompts)

        def call_with_index(index, prompt):
            try:
                result = self.chat(prompt, system_prompt, temperature)
                time.sleep(self.request_delay)
                return index, result, None
            except Exception as e:
                return index, None, str(e)

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(call_with_index, i, p): i
                for i, p in enumerate(prompts)
            }

            completed = 0
            for future in as_completed(futures):
                index, result, error = future.result()
                if error:
                    self.logger.warning(f"第{index + 1}条请求失败: {error}")
                    results[index] = {"error": error}
                else:
                    results[index] = {"content": result}

                completed += 1
                if completed % 10 == 0:
                    self.logger.info(f"批量处理进度: {completed}/{len(prompts)}")

        return results


def load_prompt_config(config_file=None):
    """加载Prompt配置文件"""
    if config_file is None:
        config_file = os.path.join(get_project_root(), 'config', 'prompts.json')

    with open(config_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def build_filter_prompt(items, config_file=None):
    """
    构建LLM过滤的Prompt

    Args:
        items: 商品列表，每项包含商品名称和目标牌名
        config_file: Prompt配置文件路径

    Returns:
        str: 构造的prompt
    """
    config = load_prompt_config(config_file)
    prompt_config = config.get('filter', {})

    system_prompt = prompt_config.get('system_prompt', '')
    user_template = prompt_config.get('user_prompt_template', '{items_text}')

    items_text = "\n".join([
        f"{i+1}. 商品名称: {item['商品名称']} | 目标牌名: {item['目标牌名']}"
        for i, item in enumerate(items)
    ])

    user_prompt = user_template.format(items_text=items_text)

    return system_prompt, user_prompt


def parse_llm_response(response_text):
    """解析LLM返回的JSON响应"""
    text = response_text.strip()
    start = text.find('[')
    end = text.rfind(']')

    if start != -1 and end != -1 and start < end:
        json_str = text[start:end+1]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON解析失败: {e}, 原始文本: {text[:500]}")

    raise ValueError(f"无法从响应中找到JSON数组: {text[:500]}")
