"""
后续可考虑引入LLM打因子标签
"""
import os
import click
import re
import tempfile
import time
from datetime import timedelta
from PyPDF2 import PdfReader, PdfWriter
from marker.config.parser import ConfigParser
from marker.config.printer import CustomClickPrinter
from marker.logger import configure_logging
from marker.models import create_model_dict
from marker.converters.pdf import PdfConverter
from marker.output import text_from_rendered

configure_logging()

def split_pdf_by_pages(pdf_path: str) -> list:
    """将PDF按页分割成多个临时文件"""
    temp_files = []
    try:
        reader = PdfReader(pdf_path)
        # 获取原始PDF的文件名（不含扩展名）
        original_name = os.path.splitext(os.path.basename(pdf_path))[0]
        
        for page_num in range(len(reader.pages)):
            writer = PdfWriter()
            writer.add_page(reader.pages[page_num])
            
            # 创建临时文件，使用原PDF名+页码编号作为文件名
            page_num_str = f"{page_num+1:02d}"  # 页码格式为两位数字，如01, 02
            temp_dir = tempfile.gettempdir()
            temp_filename = f"{original_name}_{page_num_str}.pdf"
            temp_path = os.path.join(temp_dir, temp_filename)
            
            with open(temp_path, 'wb') as f:
                writer.write(f)
            
            temp_files.append(temp_path)
    except Exception as e:
        print(f"分割PDF时出错 {pdf_path}: {str(e)}")
        # 清理已创建的临时文件
        for temp_file in temp_files:
            try:
                os.unlink(temp_file)
            except:
                pass
        return []
    return temp_files

def find_first_line_with_text(text: str, filter_text: str) -> str:
    """
    返回包含搜索文本的第一行，
    返回None表示不包含搜索文本
    """
    # 将文本分割成行
    lines = text.splitlines()
    for line in lines:
        if filter_text.lower() in line.lower():
            return line
    return None

def find_first_line_with_text_and_without(text: str, filter_text: str, filter_without: str) -> tuple:
    """
    在没搜索到排除文本的前提下，搜索到包含筛选文本的行，则返回(1, 匹配行)
    如果不符合条件则返回(0, 原因)
    """
    lines = text.splitlines()
    flag_include = False
    include_line = None

    for line in lines:
        if flag_include is False and filter_text.lower() in line.lower():
            flag_include = True
            include_line = line
            print(f"找到包含筛选文本的第一行: {include_line}")
        if filter_without.lower() in line.lower():
            print(f"找到包含排除文本的第一行: {line}，此文件将被跳过")
            return 0, "包含排除文本"
    if flag_include is False:
        print("未搜索到筛选文本，此文件将被跳过")
        return 0, "未包含筛选文本"
    print("搜索完毕，不包含排除文本，此文件符合筛选条件")
    return 1, include_line

def find_first_line_with_any_text(text: str, filter_texts: list) -> tuple:
    """
    返回包含任意一个搜索文本的第一行
    返回(匹配行, 匹配文本)，都为None表示不包含任何搜索文本
    """
    if not filter_texts:
        return None, None
        
    lines = text.splitlines()
    for line in lines:
        for filter_text in filter_texts:
            if filter_text.lower() in line.lower():
                return line, filter_text
    return None, None

def contains_any_excluded_text(text: str, excluded_texts: list) -> tuple:
    """
    检查文本是否包含任何一个排除文本
    返回(是否包含排除文本, 匹配的排除文本, 匹配行)
    """
    if not excluded_texts:
        return False, None, None
        
    lines = text.splitlines()
    for line in lines:
        for excluded_text in excluded_texts:
            if excluded_text.lower() in line.lower():
                return True, excluded_text, line
    return False, None, None

def find_text_with_multiple_conditions(text: str, filter_texts: list, filter_without_texts: list) -> tuple:
    """
    在没搜索到任何排除文本的前提下，搜索到包含任意筛选文本的行
    返回(处理结果, 匹配信息)
        处理结果: 1=符合条件, 0=不符合条件
        匹配信息: 匹配的行或不匹配的原因
    """
    # 首先检查是否包含排除文本
    contains_excluded, excluded_text, excluded_line = contains_any_excluded_text(text, filter_without_texts)
    if contains_excluded:
        print(f"找到包含排除文本 '{excluded_text}' 的行: {excluded_line}，此文件将被跳过")
        return 0, f"包含排除文本: {excluded_text}"
    
    # 然后检查是否包含任意筛选文本
    include_line, included_text = find_first_line_with_any_text(text, filter_texts)
    if include_line:
        print(f"找到包含筛选文本 '{included_text}' 的行: {include_line}")
        return 1, include_line
    else:
        print("未搜索到任何筛选文本，此文件将被跳过")
        return 0, "未包含任何筛选文本"

def process_pdf_file(file_path: str, output_dir: str, filter_text: str = None, filter_without: str = None, 
                   filter_texts: list = None, filter_without_texts: list = None, 
                   converter = None, suffix="", page_info=""):
    """
    处理单个PDF文件，检查是否符合筛选条件并保存结果
    
    Args:
        file_path: PDF文件路径
        output_dir: 输出目录
        filter_text: 要筛选的文本，None表示不筛选包含文本 (向后兼容)
        filter_without: 排除含有的文本，None表示不筛选排除文本 (向后兼容)
        filter_texts: 要筛选的文本列表，任意文本匹配即可
        filter_without_texts: 要排除的多个文本，任意匹配即排除
        converter: PDF转换器
        suffix: 输出文件名后缀
        page_info: 页面信息(用于分页处理时显示)
        
    Returns:
        tuple: (处理结果, 错误信息, 处理时间)
            处理结果: 0=跳过, 1=成功处理, -1=错误
            处理时间: 处理该文件耗时(秒)
    """
    start_time = time.time()
    
    # 处理单个文本转换为列表的情况
    if filter_text and not filter_texts:
        filter_texts = [filter_text]
    if filter_without and not filter_without_texts:
        filter_without_texts = [filter_without]
    
    try:
        # 转换PDF为文本
        rendered = converter(file_path)
        if not rendered:
            print(f"PDF转换失败: {page_info}")
            process_time = time.time() - start_time
            return -1, "转换失败", process_time
            
        text, _, _ = text_from_rendered(rendered)
        if not text.strip():
            print(f"转换后文本为空: {page_info}")
            process_time = time.time() - start_time
            return -1, "文本为空", process_time
        
        # 构建输出文件路径
        pdf_filename = os.path.basename(file_path)
        base_name = os.path.splitext(pdf_filename)[0]
        # 如果原始文件名已经包含页码后缀，则不再添加
        if not (suffix and base_name.endswith(suffix)):
            base_name = base_name + suffix
        out_path = os.path.join(output_dir, f"{base_name}.md")
        
        # 如果没有筛选条件，则默认转换所有PDF
        if (not filter_texts or len(filter_texts) == 0) and (not filter_without_texts or len(filter_without_texts) == 0):
            # 输出将要保存的路径
            print(f"将保存到: {out_path}")
            
            try:
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(text)
                process_time = time.time() - start_time
                print(f"已转换并保存: {out_path}")
                print(f"处理时间: {timedelta(seconds=process_time)}")
                return 1, None, process_time
            except IOError as e:
                process_time = time.time() - start_time
                print(f"保存文件失败 {out_path}: {str(e)}")
                return -1, f"保存失败: {str(e)}", process_time
        
        # 同时有筛选文本和排除文本
        elif filter_texts and filter_without_texts:
            ret = find_text_with_multiple_conditions(text, filter_texts, filter_without_texts)
            if ret[0] == 1:
                # 输出将要保存的路径
                print(f"将保存到: {out_path}")
                
                try:
                    with open(out_path, "w", encoding="utf-8") as f:
                        f.write(text)
                    process_time = time.time() - start_time
                    print(f"已转换并保存: {out_path}")
                    print(f"处理时间: {timedelta(seconds=process_time)}")
                    return 1, None, process_time
                except IOError as e:
                    process_time = time.time() - start_time
                    print(f"保存文件失败 {out_path}: {str(e)}")
                    return -1, f"保存失败: {str(e)}", process_time
            process_time = time.time() - start_time
            return ret[0], ret[1], process_time
            
        # 只有筛选文本
        elif filter_texts:
            matched_line, matched_text = find_first_line_with_any_text(text, filter_texts)
            if matched_line:
                # 输出将要保存的路径
                print(f"将保存到: {out_path}")
                
                try:
                    with open(out_path, "w", encoding="utf-8") as f:
                        f.write(text)
                    process_time = time.time() - start_time
                    print(f"已转换并保存: {out_path}")
                    print(f"找到包含筛选文本 '{matched_text}' 的行: {matched_line}")
                    print(f"处理时间: {timedelta(seconds=process_time)}")
                    return 1, None, process_time
                except IOError as e:
                    process_time = time.time() - start_time
                    print(f"保存文件失败 {out_path}: {str(e)}")
                    return -1, f"保存失败: {str(e)}", process_time
            else:
                process_time = time.time() - start_time
                print(f"未搜索到任何筛选文本，此文件将被跳过")
                return 0, "未包含任何筛选文本", process_time
                
        # 只有排除文本
        elif filter_without_texts:
            contains_excluded, excluded_text, excluded_line = contains_any_excluded_text(text, filter_without_texts)
            if contains_excluded:
                process_time = time.time() - start_time
                print(f"找到包含排除文本 '{excluded_text}' 的行: {excluded_line}，此文件将被跳过")
                return 0, f"包含排除文本: {excluded_text}", process_time
            else:
                # 输出将要保存的路径
                print(f"将保存到: {out_path}")
                
                try:
                    with open(out_path, "w", encoding="utf-8") as f:
                        f.write(text)
                    process_time = time.time() - start_time
                    print(f"已转换并保存: {out_path}")
                    print(f"搜索完毕，不包含任何排除文本，此文件符合筛选条件")
                    print(f"处理时间: {timedelta(seconds=process_time)}")
                    return 1, None, process_time
                except IOError as e:
                    process_time = time.time() - start_time
                    print(f"保存文件失败 {out_path}: {str(e)}")
                    return -1, f"保存失败: {str(e)}", process_time
            
    except Exception as e:
        process_time = time.time() - start_time
        print(f"处理{page_info}时出错: {str(e)}")
        return -1, str(e), process_time


@click.command(cls=CustomClickPrinter, help="Convert PDFs containing specific text to markdown.")
@click.argument("target", type=str)
@click.option("--output_dir", type=click.Path(exists=False), required=True, help="Directory to save output.")
@click.option("--filter_text", type=str, default=None, help="Text to filter PDFs by (optional, for backwards compatibility).")
@click.option("--filter_without", type=str, default=None, help="Exclude PDFs containing this text (optional, for backwards compatibility).")
@click.option("--filter_texts", type=str, multiple=True, help="Multiple texts to filter PDFs by (any match will include the PDF).")
@click.option("--filter_without_texts", type=str, multiple=True, help="Multiple texts to exclude PDFs by (any match will exclude the PDF).")
@click.option("--split_by_page", is_flag=True, default=False, help="Split PDFs by pages before processing.")
@ConfigParser.common_options
def marker_filter_cli(target: str, output_dir: str, filter_text: str = None, filter_without: str = None, 
                     filter_texts=None, filter_without_texts=None, split_by_page: bool = False, **kwargs):
    """Convert PDFs containing specific text to markdown.
    
    Args:
        target: 目标PDF文件或包含PDF文件的文件夹路径
        output_dir: 输出文件夹路径
        filter_text: 要筛选的文本（兼容旧版本）
        filter_without: 排除包含特定文本的文件（兼容旧版本）
        filter_texts: 要筛选的多个文本，任意匹配即保留
        filter_without_texts: 要排除的多个文本，任意匹配即排除
        split_by_page: 是否按页分割PDF
    """
    target = os.path.abspath(target)
    output_dir = os.path.abspath(output_dir)
    
    # 处理筛选文本和排除文本的列表
    all_filter_texts = list(filter_texts) if filter_texts else []
    all_filter_without_texts = list(filter_without_texts) if filter_without_texts else []
    
    # 如果同时使用了旧参数和新参数，合并它们
    if filter_text and filter_text not in all_filter_texts:
        all_filter_texts.append(filter_text)
    if filter_without and filter_without not in all_filter_without_texts:
        all_filter_without_texts.append(filter_without)
    
    # 显示筛选条件
    if all_filter_texts:
        print(f"筛选文本: {', '.join(all_filter_texts)}")
    if all_filter_without_texts:
        print(f"排除文本: {', '.join(all_filter_without_texts)}")
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # 获取要处理的PDF文件列表
    if os.path.isfile(target) and target.lower().endswith('.pdf'):
        pdf_files = [target]
    elif os.path.isdir(target):
        pdf_files = [os.path.join(target, f) for f in os.listdir(target) if f.lower().endswith('.pdf')]
    else:
        print(f"错误: {target} 不是有效的PDF文件或文件夹")
        return
    
    if not pdf_files:
        print(f"警告: 在 {target} 中没有找到PDF文件")
        return
    
    # Initialize converter
    models = create_model_dict()
    config_parser = ConfigParser(kwargs)
    converter_cls = config_parser.get_converter_cls()
    converter = converter_cls(
        config=config_parser.generate_config_dict(),
        artifact_dict=models,
        processor_list=config_parser.get_processors(),
        renderer=config_parser.get_renderer(),
        llm_service=config_parser.get_llm_service()
    )
    
    # 处理每个PDF文件
    processed_count = 0
    error_count = 0
    skipped_count = 0
    total_files = len(pdf_files)
    processing_times = []
    
    start_time = time.time()
    
    for pdf_path in pdf_files:
        print("---------------------------------------------------------")
        pdf_file = os.path.basename(pdf_path)
        try:
            # 检查文件是否存在且可读
            if not os.path.exists(pdf_path):
                print(f"文件不存在: {pdf_file}")
                skipped_count += 1
                continue
                
            if not os.access(pdf_path, os.R_OK):
                print(f"文件无法读取: {pdf_file}")
                skipped_count += 1
                continue
            
            # 如果需要按页分割
            if split_by_page:
                print(f"正在分割PDF: {pdf_file}")
                temp_files = split_pdf_by_pages(pdf_path)
                if not temp_files:
                    print(f"分割PDF失败: {pdf_file}")
                    error_count += 1
                    continue
                
                # 处理每个分割后的页面
                page_processing_times = []
                for i, temp_file in enumerate(temp_files):
                    try:
                        page_info = f"第{i+1}页"
                        page_num_str = f"{i+1:02d}"  # 页码格式为两位数字，如01, 02
                        print(f"\n正在处理{page_info}: {temp_file}")
                        
                        # 使用封装的函数处理PDF
                        # 从临时文件名获取原始基本名称
                        temp_basename = os.path.basename(temp_file)
                        # 不需要再添加页码后缀，因为临时文件名已经包含
                        result = process_pdf_file(
                            temp_file, 
                            output_dir, 
                            filter_texts=all_filter_texts,
                            filter_without_texts=all_filter_without_texts,
                            converter=converter, 
                            suffix="",  # 不再添加额外后缀
                            page_info=page_info
                        )
                        
                        if isinstance(result, tuple) and len(result) >= 3:
                            status, _, process_time = result
                            page_processing_times.append(process_time)
                        else:
                            # 向后兼容旧版本
                            status = result[0] if isinstance(result, tuple) else result
                            
                        if status == 1:
                            processed_count += 1
                        elif status == -1:
                            error_count += 1
                        else:
                            skipped_count += 1
                            
                    finally:
                        # 清理临时文件
                        try:
                            os.unlink(temp_file)
                        except:
                            pass
                
                # 记录整个PDF的处理时间（所有页面的总和）
                if page_processing_times:
                    processing_times.append(sum(page_processing_times))
            else:
                # 直接处理整个PDF
                print(f"\n正在处理: {pdf_file}")
                
                # 使用封装的函数处理PDF
                result = process_pdf_file(
                    pdf_path, 
                    output_dir,
                    filter_texts=all_filter_texts,
                    filter_without_texts=all_filter_without_texts,
                    converter=converter, 
                    page_info=pdf_file
                )
                
                if isinstance(result, tuple) and len(result) >= 3:
                    status, _, process_time = result
                    processing_times.append(process_time)
                else:
                    # 向后兼容旧版本
                    status = result[0] if isinstance(result, tuple) else result
                
                if status == 1:
                    processed_count += 1
                elif status == -1:
                    error_count += 1
                else:
                    skipped_count += 1
                
        except Exception as e:
            print(f"处理{pdf_file}时出错: {str(e)}")
            error_count += 1
        print("---------------------------------------------------------")
    
    end_time = time.time()
    total_time = end_time - start_time
    
    # 计算统计数据
    if processing_times:
        average_time = sum(processing_times) / len(processing_times)
        min_time = min(processing_times)
        max_time = max(processing_times)
    else:
        average_time = min_time = max_time = 0
    
    # 打印处理统计信息
    print(f"\n处理完成:")
    print(f"成功处理: {processed_count} 个文件")
    print(f"处理失败: {error_count} 个文件") 
    print(f"已跳过: {skipped_count} 个文件")
    print(f"总时间: {timedelta(seconds=int(total_time))}")
    print(f"平均处理时间: {timedelta(seconds=int(average_time))}")
    print(f"最短处理时间: {timedelta(seconds=int(min_time))}")
    print(f"最长处理时间: {timedelta(seconds=int(max_time))}")
    if processed_count + error_count + skipped_count > 0:
        success_rate = processed_count / (processed_count + error_count + skipped_count) * 100
        print(f"处理成功率: {success_rate:.2f}%")

if __name__ == "__main__":
    marker_filter_cli() 