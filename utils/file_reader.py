import pandas as pd
import json
import io


def read_uploaded_file(uploaded_file):
    """
    统一读取上传的文件，支持 csv, xlsx, xls, txt, json 格式。
    返回 pandas DataFrame。
    如果失败返回 None 和错误信息。
    """
    try:
        filename = uploaded_file.name.lower()

        if filename.endswith('.csv'):
            # 尝试多种编码
            for encoding in ['utf-8', 'gbk', 'gb2312', 'utf-8-sig', 'latin1']:
                try:
                    uploaded_file.seek(0)
                    df = pd.read_csv(uploaded_file, encoding=encoding)
                    if len(df.columns) == 1:
                        # 可能是分号或制表符分隔，重试
                        uploaded_file.seek(0)
                        df = pd.read_csv(uploaded_file, encoding=encoding, sep=None, engine='python')
                    return df, None
                except (UnicodeDecodeError, UnicodeError):
                    continue
                except Exception as e:
                    # 编码正确但解析出错
                    return None, f"CSV解析错误: {str(e)}"
            return None, "无法识别文件编码，请尝试将文件另存为 UTF-8 编码"

        elif filename.endswith(('.xlsx', '.xls')):
            uploaded_file.seek(0)
            df = pd.read_excel(uploaded_file)
            return df, None

        elif filename.endswith('.txt'):
            for encoding in ['utf-8', 'gbk', 'gb2312', 'utf-8-sig', 'latin1']:
                try:
                    uploaded_file.seek(0)
                    content = uploaded_file.read().decode(encoding)
                    # 自动检测分隔符
                    if '\t' in content:
                        df = pd.read_csv(io.StringIO(content), sep='\t')
                    elif ',' in content:
                        df = pd.read_csv(io.StringIO(content), sep=',')
                    else:
                        df = pd.read_csv(io.StringIO(content), sep=None, engine='python')
                    return df, None
                except (UnicodeDecodeError, UnicodeError):
                    continue
            return None, "无法识别TXT文件编码"

        elif filename.endswith('.json'):
            uploaded_file.seek(0)
            for encoding in ['utf-8', 'gbk', 'utf-8-sig']:
                try:
                    content = uploaded_file.read().decode(encoding)
                    data = json.loads(content)
                    if isinstance(data, list):
                        df = pd.DataFrame(data)
                    elif isinstance(data, dict):
                        # 尝试把 dict 转为 DataFrame
                        df = pd.DataFrame([data]) if not any(isinstance(v, list) for v in data.values()) else pd.DataFrame(data)
                    else:
                        return None, "JSON格式不支持，请提供数组或对象格式"
                    return df, None
                except (UnicodeDecodeError, UnicodeError):
                    uploaded_file.seek(0)
                    continue
            return None, "无法识别JSON文件编码"
        else:
            return None, f"不支持的文件格式: {filename.split('.')[-1]}"

    except Exception as e:
        return None, f"文件读取失败: {str(e)}"
