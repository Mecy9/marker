# Marker 使用指南

Marker 是一个强大的文档转换工具，能够快速准确地将 PDF、图像、PPTX、DOCX、XLSX、HTML、EPUB 等文件转换为 Markdown、JSON 和 HTML 格式，支持多语言处理、表格格式化、数学公式识别和图像提取等功能。

## 基本使用方法

### marker_filter 命令
```bash
marker_filter 目标报告文件夹路径 --output_dir 输出文件夹路径 --filter_text 需要包含的文本 --filter_without 不包含的文本 --split_by_page
```

**参数说明：**
- `--filter_text`：需要包含的文本（可选）
- `--filter_without`：不包含的文本（可选）
- `--split_by_page`：按页分割（可选）

更多参数可以查看 `--help`，或者查看marker的官方文档：[https://github.com/VikParuchuri/marker](https://github.com/VikParuchuri/marker)

### 高级筛选功能

#### 多文本筛选
- `--filter_texts` 和 `--filter_without_texts`：可以指定多个筛选文本
- 只要PDF中包含任意一个筛选文本，就会被处理
- 匹配是不区分大小写的
- 每个 `--filter_texts` 参数可以指定一个文本

#### 引号使用规则
- 如果文本中包含空格，必须加引号
- 如果文本是纯中文或纯英文且没有空格，可以不加引号
- 如果文本包含特殊字符，建议加引号

### 使用示例

#### 筛选包含多个关键词的PDF
```bash
marker_filter D:\material\因子日历2024\因子日历202401.pdf --output_dir ./test --filter_texts "因子" --filter_texts "日历" --filter_texts "2024"
```

## 完整命令参考

### marker_single 命令
转换单个文件：

```bash
marker_single /path/to/file.pdf
```

**主要选项：**
- `--output_dir PATH`：输出文件保存目录，默认为settings.OUTPUT_DIR指定的值
- `--output_format [markdown|json|html]`：指定输出格式
- `--paginate_output`：分页输出，使用 `\n\n{PAGE_NUMBER}` 后跟 `-` * 48，然后 `\n\n`
- `--use_llm`：使用LLM提高准确性，必须设置 `GOOGLE_API_KEY` 环境变量
- `--redo_inline_math`：如需最高质量的内联数学转换，与 `--use_llm` 一起使用
- `--disable_image_extraction`：不提取PDF中的图像
- `--page_range TEXT`：指定要处理的页面，接受逗号分隔的页码和范围，例如：`--page_range "0,5-10,20"`
- `--force_ocr`：强制对整个文档进行OCR处理
- `--strip_existing_ocr`：移除文档中所有现有的OCR文本并重新OCR
- `--debug`：启用调试模式
- `--processors TEXT`：通过提供完整模块路径覆盖默认处理器
- `--config_json PATH`：包含其他设置的JSON配置文件路径
- `--languages TEXT`：可选指定OCR处理使用的语言，接受逗号分隔列表
- `--converter_cls`：转换器类，默认为 `marker.converters.pdf.PdfConverter`
- `--llm_service`：如果传递 `--use_llm` 时使用的LLM服务

### marker 命令
转换多个文件：

```bash
marker /path/to/input/folder --workers 4
```

**选项：**
- 支持所有 `marker_single` 的选项
- `--workers`：同时运行的转换工作进程数，默认为5

### marker_chunk_convert 命令
在多GPU上转换多个文件：

```bash
NUM_DEVICES=4 NUM_WORKERS=15 marker_chunk_convert ../pdf_in ../md_out
```

**参数：**
- `NUM_DEVICES`：使用的GPU数量，应为2或更大
- `NUM_WORKERS`：每个GPU上运行的并行进程数

## 输出格式

### Markdown
- 包含图像链接（图像保存在同一文件夹中）
- 格式化表格
- 嵌入LaTeX方程（用 `$$` 包围）
- 代码用三重反引号包围
- 脚注使用上标

### HTML
- 图像通过 `img` 标签包含
- 方程用 `<math>` 标签包围
- 代码在 `pre` 标签中

### JSON
- 以树状结构组织
- 叶节点是块，如单个列表项、文本段落或图像
- 每个列表项代表一个页面
- 包含 `id`、`block_type`、`html`、`polygon`、`children` 等字段


## 安装部署

### 环境准备
建议创建新的虚拟环境进行部署：

```bash
conda create -n marker_env python=3.11
conda activate marker_env
```

### 安装步骤
1. 在你期望的路径下保存marker文件夹，此处以D盘为例
2. 进入marker目录：`cd D:\marker`
3. 安装依赖：`pip install -e .`

### 验证安装
```bash
marker_filter --help
```


## LLM服务

使用 `--use_llm` 标志时，可以选择以下服务：

- **Gemini**：默认使用Gemini开发者API，需要传递 `--gemini_api_key`
- **Google Vertex**：使用vertex，更可靠，需要传递 `--vertex_project_id`
- **Ollama**：使用本地模型，可配置 `--ollama_base_url` 和 `--ollama_model`
- **Claude**：使用anthropic API，可配置 `--claude_api_key` 和 `--claude_model_name`
- **OpenAI**：支持任何openai-like端点，可配置 `--openai_api_key`、`--openai_model` 和 `--openai_base_url`

## 故障排除

如果遇到问题，可以尝试以下设置：

- 如果准确性有问题，尝试设置 `--use_llm` 使用LLM提高质量
- 如果看到乱码文本，确保设置 `force_ocr` 重新OCR文档
- 设置 `TORCH_DEVICE` 强制marker使用给定的torch设备进行推理
- 如果出现内存不足错误，减少工作进程数，也可以尝试将长PDF拆分为多个文件

## 调试

传递 `debug` 选项激活调试模式，这将保存每页的检测布局和文本图像，并输出包含额外边界框信息的JSON文件。 