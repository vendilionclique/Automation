"""
检查点模块
负责进度追踪和断点续传
"""
import os
import json
import shutil
import tempfile
from datetime import datetime


class CheckpointManager:
    """检查点管理器"""

    def __init__(self, checkpoint_dir='data/checkpoints'):
        """
        初始化检查点管理器

        Args:
            checkpoint_dir: 检查点文件目录
        """
        self.checkpoint_dir = checkpoint_dir
        os.makedirs(checkpoint_dir, exist_ok=True)
        self.checkpoint_file = None
        self.data = None

    def create(self, input_file, keywords, checkpoint_file=None):
        """
        创建新的检查点

        Args:
            input_file: 输入文件路径
            keywords: 关键词列表
            checkpoint_file: 检查点文件名（默认自动生成）
        """
        if checkpoint_file:
            self.checkpoint_file = os.path.join(self.checkpoint_dir, checkpoint_file)
        else:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            self.checkpoint_file = os.path.join(self.checkpoint_dir, f'progress_{timestamp}.json')

        self.data = {
            'input_file': input_file,
            'started_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total_keywords': len(keywords),
            'keywords': keywords,
            'processed': [],
            'failed': [],
            'results': {}
        }
        self._save()
        print(f"检查点已创建: {self.checkpoint_file}")
        print(f"  待处理关键词: {len(keywords)}")

    def load(self, checkpoint_file):
        """
        加载已有的检查点

        Args:
            checkpoint_file: 检查点文件名或完整路径

        Returns:
            dict: 检查点数据，如果文件不存在则返回None
        """
        if not os.path.isabs(checkpoint_file):
            checkpoint_file = os.path.join(self.checkpoint_dir, checkpoint_file)

        if not os.path.exists(checkpoint_file):
            print(f"检查点文件不存在: {checkpoint_file}")
            return None

        with open(checkpoint_file, 'r', encoding='utf-8') as f:
            self.data = json.load(f)

        self.checkpoint_file = checkpoint_file
        remaining = self.data['total_keywords'] - len(self.data['processed'])
        print(f"检查点已加载: {checkpoint_file}")
        print(f"  总关键词: {self.data['total_keywords']}")
        print(f"  已处理: {len(self.data['processed'])}")
        print(f"  失败: {len(self.data['failed'])}")
        print(f"  剩余: {remaining}")
        return self.data

    def find_latest(self):
        """
        查找最新的检查点文件

        Returns:
            str: 最新检查点文件路径，无则返回None
        """
        if not os.path.exists(self.checkpoint_dir):
            return None

        checkpoint_files = [
            f for f in os.listdir(self.checkpoint_dir)
            if f.startswith('progress_') and f.endswith('.json')
        ]

        if not checkpoint_files:
            return None

        # 按修改时间排序，最新的在前
        checkpoint_files.sort(
            key=lambda f: os.path.getmtime(os.path.join(self.checkpoint_dir, f)),
            reverse=True
        )
        return os.path.join(self.checkpoint_dir, checkpoint_files[0])

    def get_remaining_keywords(self):
        """
        获取未处理的关键词列表

        Returns:
            list: 未处理的关键词
        """
        if not self.data:
            return []
        processed = set(self.data['processed'])
        return [kw for kw in self.data['keywords'] if kw not in processed]

    def mark_processed(self, keyword, result=None):
        """
        标记关键词为已处理

        Args:
            keyword: 搜索关键词
            result: 处理结果字典（包含文件路径、价格等）
        """
        if not self.data:
            return

        if keyword not in self.data['processed']:
            self.data['processed'].append(keyword)

        # 从失败列表中移除（如果之前失败过重试成功）
        if keyword in self.data['failed']:
            self.data['failed'].remove(keyword)

        if result:
            result['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.data['results'][keyword] = result

        self.data['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self._save()

    def mark_failed(self, keyword, error='未知错误'):
        """
        标记关键词为失败

        Args:
            keyword: 搜索关键词
            error: 错误信息
        """
        if not self.data:
            return

        if keyword not in self.data['failed']:
            self.data['failed'].append(keyword)

        if keyword not in self.data['results']:
            self.data['results'][keyword] = {
                'status': 'failed',
                'error': error,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }

        self.data['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self._save()

    def get_progress(self):
        """
        获取当前进度摘要

        Returns:
            dict: 进度信息
        """
        if not self.data:
            return {}

        return {
            'total': self.data['total_keywords'],
            'processed': len(self.data['processed']),
            'failed': len(self.data['failed']),
            'remaining': self.data['total_keywords'] - len(self.data['processed']),
            'started_at': self.data['started_at'],
            'last_updated': self.data['last_updated']
        }

    def _save(self):
        """保存检查点到文件（原子写入）"""
        if not self.checkpoint_file or not self.data:
            return

        # 原子写入：先写临时文件再重命名
        try:
            fd, temp_path = tempfile.mkstemp(
                dir=self.checkpoint_dir, suffix='.tmp'
            )
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            shutil.move(temp_path, self.checkpoint_file)
        except Exception as e:
            print(f"保存检查点失败: {e}")
