"""兼容垫片：将旧名称 evaluate_statistical_prices 转发到新实现。"""

from modules.price_cluster_eval import evaluate_price_clusters


def evaluate_statistical_prices(input_file, output_file=None, logger=None):
    return evaluate_price_clusters(
        input_file=input_file,
        output_file=output_file,
        logger=logger,
    )
