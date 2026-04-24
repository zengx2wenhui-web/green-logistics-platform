# 文件读取工具
import io
import json
import logging
import unicodedata
from typing import Tuple, Optional, Dict, List, Set

import pandas as pd

logger = logging.getLogger(__name__)

# 全局配置
_MAX_FILE_SIZE_MB: float = 10.0
_MAX_ROW_COUNT: int = 200  # VRP 求解规模限制
TEXT_FILE_ENCODINGS: Tuple[str, ...] = (
    "utf-8-sig",
    "utf-8",
    "gb18030",
    "gbk",
    "gb2312",
)
_DANGEROUS_EXTENSIONS: Set[str] = {
    ".exe", ".bat", ".cmd", ".sh", ".ps1", ".js", ".vbs",
    ".dll", ".so", ".bin", ".msi", ".py", ".pyw", ".jar",
    ".com", ".scr", ".wsf", ".cpl",
}

# 列名别名映射，将用户可能使用的五花八门的列名统一转换为系统标准名
_COLUMN_ALIAS_MAP: Dict[str, List[str]] = {
    "场馆名称": ["场馆名", "场馆", "名称", "venue", "venue_name", "name"],
    "地址": ["详细地址", "address", "场馆地址", "addr", "位置"],
    "承办项目": ["项目", "运动项目", "sport", "project", "event"],
    "经度": ["lng", "longitude", "lon", "x"],
    "纬度": ["lat", "latitude", "y"],
    "需求量": ["需求", "需求量_kg", "demand", "weight", "重量", "weight_kg"],
}

# 映射后的标准列名
_REQUIRED_COLUMNS: List[str] = ["场馆名称", "地址"]


# 纯粹的 I/O 读取工具
def read_uploaded_file(
    uploaded_file,
) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    try:
        filename: str = uploaded_file.name.lower()
        ext = "." + filename.rsplit(".", 1)[-1] if "." in filename else ""

        if ext in _DANGEROUS_EXTENSIONS:
            return None, f"不允许上传 {ext} 类型文件，请使用 CSV/Excel/JSON 格式"

        if ext == ".csv":
            return _read_csv(uploaded_file)
        elif ext in (".xlsx", ".xls"):
            uploaded_file.seek(0)
            df = pd.read_excel(uploaded_file)
            return df, None
        elif ext == ".txt":
            return _read_txt(uploaded_file)
        elif ext == ".json":
            return _read_json(uploaded_file)
        else:
            return None, f"不支持的文件格式: {ext or '未知'}，请使用 CSV/Excel/JSON"

    except Exception as e:
        logger.error(f"[文件读取] 未预期错误: {e}")
        return None, f"文件读取失败: {str(e)}"


# 读取 CSV 文件
def _read_csv(uploaded_file) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    last_error: Optional[str] = None
    for encoding in TEXT_FILE_ENCODINGS:
        try:
            uploaded_file.seek(0)
            df = pd.read_csv(uploaded_file, encoding=encoding)
            if len(df.columns) == 1:
                uploaded_file.seek(0)
                df = pd.read_csv(
                    uploaded_file, encoding=encoding,
                    sep=None, engine="python",
                )
            return df, None
        except (UnicodeDecodeError, UnicodeError):
            continue
        except pd.errors.ParserError as e:
            last_error = f"CSV 解析错误: {e}"
            continue
        except Exception as e:
            return None, f"CSV 读取失败: {e}"
    return None, last_error or "无法识别文件编码，请将文件另存为 UTF-8 编码后重试"


# 读取 TXT 文件
def _read_txt(uploaded_file) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    for encoding in TEXT_FILE_ENCODINGS:
        try:
            uploaded_file.seek(0)
            content = uploaded_file.read().decode(encoding)
            if "\t" in content:
                df = pd.read_csv(io.StringIO(content), sep="\t")
            elif "," in content:
                df = pd.read_csv(io.StringIO(content), sep=",")
            else:
                df = pd.read_csv(
                    io.StringIO(content), sep=None, engine="python",
                )
            return df, None
        except (UnicodeDecodeError, UnicodeError):
            continue
    return None, "无法识别 TXT 文件编码"


# 读取 JSON 文件
def _read_json(uploaded_file) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    for encoding in TEXT_FILE_ENCODINGS:
        try:
            uploaded_file.seek(0)
            content = uploaded_file.read().decode(encoding)
            data = json.loads(content)
            if isinstance(data, list):
                df = pd.DataFrame(data)
            elif isinstance(data, dict):
                has_list = any(isinstance(v, list) for v in data.values())
                df = pd.DataFrame(data) if has_list else pd.DataFrame([data])
            else:
                return None, "JSON 格式不支持，请提供数组或对象格式"
            return df, None
        except (UnicodeDecodeError, UnicodeError):
            uploaded_file.seek(0)
            continue
    return None, "无法识别 JSON 文件编码"


# 文件读取与数据清洗
class LogisticsDataProcessor:
    def __init__(
        self,
        max_file_size_mb: float = _MAX_FILE_SIZE_MB,
        max_row_count: int = _MAX_ROW_COUNT,
        required_columns: Optional[List[str]] = None,
        column_alias_map: Optional[Dict[str, List[str]]] = None,
    ):
        self.max_file_size_mb = max_file_size_mb
        self.max_row_count = max_row_count
        self.required_columns = required_columns or _REQUIRED_COLUMNS
        self.alias_map = column_alias_map or _COLUMN_ALIAS_MAP

    def process(
        self, uploaded_file,
    ) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
        # 第一层: 安全拦截
        err = self._check_file_safety(uploaded_file)
        if err:
            return None, err

        # 第四层: 底层读取
        df, err = read_uploaded_file(uploaded_file)
        if err:
            return None, err

        # 空数据拦截
        if df is None or df.empty:
            return None, "文件为空或仅包含表头，请在文件中添加数据行"

        # 行数检查
        if len(df) > self.max_row_count:
            return None, (
                f"数据行数 ({len(df)}) 超过上限 ({self.max_row_count})。"
                f"物流 VRP 求解建议控制在 {self.max_row_count} 个节点以内"
            )

        df = self._apply_column_aliases(df)
        missing = self._check_required_columns(df)
        if missing:
            return None, (
                f"缺少必填列: {', '.join(missing)}。"
                f"请确保文件包含以下列: {', '.join(self.required_columns)}"
            )

        df = self._clean_data(df)
        return df, None

    # 检查文件大小
    def _check_file_safety(self, uploaded_file) -> Optional[str]:
        uploaded_file.seek(0, 2)
        size_mb = uploaded_file.tell() / (1024 * 1024)
        uploaded_file.seek(0)
        if size_mb > self.max_file_size_mb:
            return (
                f"文件大小 ({size_mb:.1f} MB) 超过限制 "
                f"({self.max_file_size_mb} MB)"
            )
        return None

    def _apply_column_aliases(self, df: pd.DataFrame) -> pd.DataFrame:
        rename_map: Dict[str, str] = {}
        for standard_name, aliases in self.alias_map.items():
            if standard_name in df.columns:
                continue
            for alias in aliases:
                for col in df.columns:
                    if col.strip().lower() == alias.lower():
                        rename_map[col] = standard_name
                        break
                if standard_name in rename_map.values():
                    break
        if rename_map:
            df = df.rename(columns=rename_map)
        return df

    def _check_required_columns(self, df: pd.DataFrame) -> List[str]:
        return [col for col in self.required_columns if col not in df.columns]

    def _clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        # 去除全空行
        df = df.dropna(how="all")

        # 关键列为空则剔除（无地址无法地理编码）
        if "地址" in df.columns:
            df = df[df["地址"].notna() & (df["地址"].astype(str).str.strip() != "")]

        # 字符串列去首尾空格
        str_cols = df.select_dtypes(include=["object"]).columns
        for col in str_cols:
            df[col] = df[col].astype(str).str.strip()

        # 数值列异常修复（负数截断为 0）
        for col in ("需求量", "经度", "纬度"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        if "需求量" in df.columns:
            df["需求量"] = df["需求量"].clip(lower=0)

        df = df.reset_index(drop=True)
        return df

# 字符串规范化工具
def normalize_name(name: str) -> str:
    if name is None:
        return ""
    s = str(name)
    try:
        s = unicodedata.normalize("NFKC", s)
    except Exception:
        pass
    s = s.replace("\u3000", " ")
    s = s.strip()
    s = " ".join(s.split())
    return s
