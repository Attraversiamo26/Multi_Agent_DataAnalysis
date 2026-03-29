import pandas as pd
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class DataProcessor:
    """数据处理器，专门用于清理列名"""
    
    def __init__(self):
        pass
    
    def clean_column_names(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        清理列名，移除换行符、空格和其他特殊字符
        适用于所有用户上传的数据
        
        Args:
            df: 需要清理列名的DataFrame
            
        Returns:
            列名已清理的DataFrame
        """
        # 安全检查：确保 df 是 DataFrame
        if not isinstance(df, pd.DataFrame):
            logger.warning(f"clean_column_names: 输入不是 DataFrame，而是 {type(df)}")
            # 如果是字典，尝试取第一个值
            if isinstance(df, dict) and df:
                first_key = list(df.keys())[0]
                df = df[first_key]
                logger.warning(f"clean_column_names: 从字典中提取了第一个 sheet: {first_key}")
            else:
                raise TypeError(f"需要 pandas DataFrame，但得到的是 {type(df)}")
        
        df.columns = [
            str(col)
            .replace('\n', '')
            .replace('\r', '')
            .replace('\t', '')
            .replace(' ', '')
            .strip()
            for col in df.columns
        ]
        return df


# 全局实例
_data_processor = None


def get_data_processor() -> DataProcessor:
    """获取数据处理器单例"""
    global _data_processor
    if _data_processor is None:
        _data_processor = DataProcessor()
    return _data_processor