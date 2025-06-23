import streamlit as st
from PIL import Image, ImageDraw
import requests
from io import BytesIO
import os  # 确保os模块在这里导入
# 移除cairosvg依赖，使用svglib作为唯一的SVG处理库
try:
    from svglib.svglib import svg2rlg
    from reportlab.graphics import renderPM
    SVGLIB_AVAILABLE = True
except ImportError:
    SVGLIB_AVAILABLE = False
    st.warning("SVG processing libraries not installed, SVG conversion will not be available")
from openai import OpenAI
from streamlit_image_coordinates import streamlit_image_coordinates
import re
import math
# 导入面料纹理模块
from fabric_texture import apply_fabric_texture
import uuid
import json
# 导入并行处理库
import concurrent.futures
import time
import threading

# API配置信息 - 多个API密钥用于增强并发能力
API_KEYS = [
    "sk-lNVAREVHjj386FDCd9McOL7k66DZCUkTp6IbV0u9970qqdlg",
    "sk-y8x6LH0zdtyQncT0aYdUW7eJZ7v7cuKTp90L7TiK3rPu3fAg", 
    "sk-Kp59pIj8PfqzLzYaAABh2jKsQLB0cUKU3n8l7TIK3rpU61QG",
    "sk-KACPocnavR6poutXUaj7HxsqUrxvcV808S2bv0U9974Ec83g",
    "sk-YknuN0pb6fKBOP6xFOqAdeeqhoYkd1cEl9380vC5HHeC2B30"
]
BASE_URL = "https://api.deepbricks.ai/v1/"

# GPT-4o-mini API配置 - 同样使用多个密钥
GPT4O_MINI_API_KEYS = [
    "sk-lNVAREVHjj386FDCd9McOL7k66DZCUkTp6IbV0u9970qqdlg",
    "sk-y8x6LH0zdtyQncT0aYdUW7eJZ7v7cuKTp90L7TiK3rPu3fAg",
    "sk-Kp59pIj8PfqzLzYaAABh2jKsQLB0cUKU3n8l7TIK3rpU61QG", 
    "sk-KACPocnavR6poutXUaj7HxsqUrxvcV808S2bv0U9974Ec83g",
    "sk-YknuN0pb6fKBOP6xFOqAdeeqhoYkd1cEl9380vC5HHeC2B30"
]
GPT4O_MINI_BASE_URL = "https://api.deepbricks.ai/v1/"

# API密钥轮询计数器
_api_key_counter = 0
_gpt4o_api_key_counter = 0
_api_lock = threading.Lock()

def get_next_api_key():
    """获取下一个DALL-E API密钥（轮询方式）"""
    global _api_key_counter
    with _api_lock:
        key = API_KEYS[_api_key_counter % len(API_KEYS)]
        _api_key_counter += 1
        return key

def get_next_gpt4o_api_key():
    """获取下一个GPT-4o-mini API密钥（轮询方式）"""
    global _gpt4o_api_key_counter
    with _api_lock:
        key = GPT4O_MINI_API_KEYS[_gpt4o_api_key_counter % len(GPT4O_MINI_API_KEYS)]
        _gpt4o_api_key_counter += 1
        return key

# 自定义SVG转PNG函数，不依赖外部库
def convert_svg_to_png(svg_content):
    """
    将SVG内容转换为PNG格式的PIL图像对象
    使用svglib库来处理，不再依赖cairosvg
    """
    try:
        if SVGLIB_AVAILABLE:
            # 使用svglib将SVG内容转换为PNG
            from io import BytesIO
            svg_bytes = BytesIO(svg_content)
            drawing = svg2rlg(svg_bytes)
            png_bytes = BytesIO()
            renderPM.drawToFile(drawing, png_bytes, fmt="PNG")
            png_bytes.seek(0)
            return Image.open(png_bytes).convert("RGBA")
        else:
            st.error("SVG conversion libraries not available. Please install svglib and reportlab.")
            return None
    except Exception as e:
        st.error(f"Error converting SVG to PNG: {str(e)}")
        return None

# 设置默认生成的设计数量，取代UI上的选择按钮
DEFAULT_DESIGN_COUNT = 1  # 可以设置为1, 3, 5，分别对应原来的low, medium, high

def get_ai_design_suggestions(user_preferences=None):
    """Get design suggestions from GPT-4o-mini with more personalized features"""
    client = OpenAI(api_key=get_next_gpt4o_api_key(), base_url=GPT4O_MINI_BASE_URL)
    
    # Default prompt if no user preferences provided
    if not user_preferences:
        user_preferences = "casual fashion t-shirt design"
    
    # Construct the prompt
    prompt = f"""
    As a design consultant, please provide personalized design suggestions for a "{user_preferences}" style.
    
    Please provide the following design suggestions in JSON format:

    1. Color: Select the most suitable color for this style (provide name and hex code)
    2. Fabric: Select the most suitable fabric type (Cotton, Polyester, Cotton-Polyester Blend, Jersey, Linen, or Bamboo)
    3. Text: A suitable phrase or slogan that matches the style (keep it concise and impactful)
    4. Logo: A brief description of a logo element that would complement the design

    Return your response as a valid JSON object with the following structure:
    {{
        "color": {{
            "name": "Color name",
            "hex": "#XXXXXX"
        }},
        "fabric": "Fabric type",
        "text": "Suggested text or slogan",
        "logo": "Logo/graphic description"
    }}
    """
    
    try:
        # 调用GPT-4o-mini
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a professional design consultant. Provide design suggestions in JSON format exactly as requested."},
                {"role": "user", "content": prompt}
            ]
        )
        
        # 返回建议内容
        if response.choices and len(response.choices) > 0:
            suggestion_text = response.choices[0].message.content
            
            # 尝试解析JSON
            try:
                # 查找JSON格式的内容
                json_match = re.search(r'```json\s*(.*?)\s*```', suggestion_text, re.DOTALL)
                if json_match:
                    suggestion_json = json.loads(json_match.group(1))
                else:
                    # 尝试直接解析整个内容
                    suggestion_json = json.loads(suggestion_text)
                
                return suggestion_json
            except Exception as e:
                print(f"Error parsing JSON: {e}")
                return {"error": f"Failed to parse design suggestions: {str(e)}"}
        else:
            return {"error": "Failed to get AI design suggestions. Please try again later."}
    except Exception as e:
        return {"error": f"Error getting AI design suggestions: {str(e)}"}

def generate_vector_image(prompt, background_color=None):
    """Generate an image based on the prompt with specified background color"""
    client = OpenAI(api_key=get_next_api_key(), base_url=BASE_URL)
    
    # 如果提供了背景颜色，在提示中明确指定
    color_prompt = ""
    if background_color:
        # 更加强调颜色匹配，指定确切的HEX色号
        color_prompt = f" with EXACT RGB background color HEX:{background_color} (you MUST use this exact HEX color code for the background)"
    
    # 添加禁止生成T恤或服装的提示
    prohibition = " DO NOT include any t-shirts, clothing, mockups, or how the design would look when applied to products. Create ONLY the standalone graphic."
    
    try:
        resp = client.images.generate(
            model="dall-e-3",
            prompt=prompt + f" (Make sure the image has a solid{color_prompt} background, NOT transparent. Color matching is CRITICAL - background must be EXACTLY {background_color}!){prohibition}",
            n=1,
            size="1024x1024",
            quality="standard"
        )
    except Exception as e:
        st.error(f"Error calling API: {e}")
        return None

    if resp and len(resp.data) > 0 and resp.data[0].url:
        image_url = resp.data[0].url
        try:
            image_resp = requests.get(image_url)
            if image_resp.status_code == 200:
                content_type = image_resp.headers.get("Content-Type", "")
                if "svg" in content_type.lower():
                    # 使用更新后的SVG处理函数
                    return convert_svg_to_png(image_resp.content)
                else:
                    # 确保图像没有透明背景，使用指定的背景色
                    img = Image.open(BytesIO(image_resp.content)).convert("RGBA")
                    
                    # 如果提供了背景颜色，使用指定颜色；否则使用白色
                    if background_color:
                        # 转换十六进制颜色为RGB
                        bg_color = tuple(int(background_color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4)) + (255,)
                    else:
                        bg_color = (255, 255, 255, 255)
                    
                    # 创建指定背景色的背景图像
                    color_bg = Image.new("RGBA", img.size, bg_color)
                    # 合成图像，消除透明度
                    img = Image.alpha_composite(color_bg, img)
                    return img
            else:
                st.error(f"Failed to download image, status code: {image_resp.status_code}")
        except Exception as download_err:
            st.error(f"Error requesting image: {download_err}")
    else:
        st.error("Could not get image URL from API response.")
    return None

def change_shirt_color(image, color_hex, apply_texture=False, fabric_type=None):
    """Change T-shirt color with optional fabric texture"""
    # 转换十六进制颜色为RGB
    color_rgb = tuple(int(color_hex.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
    
    # 创建副本避免修改原图
    colored_image = image.copy().convert("RGBA")
    
    # 获取图像数据
    data = colored_image.getdata()
    
    # 创建新数据
    new_data = []
    # 白色阈值 - 调整这个值可以控制哪些像素被视为白色/浅色并被改变
    threshold = 200
    
    for item in data:
        # 判断是否是白色/浅色区域 (RGB值都很高)
        if item[0] > threshold and item[1] > threshold and item[2] > threshold and item[3] > 0:
            # 保持原透明度，改变颜色
            new_color = (color_rgb[0], color_rgb[1], color_rgb[2], item[3])
            new_data.append(new_color)
        else:
            # 保持其他颜色不变
            new_data.append(item)
    
    # 更新图像数据
    colored_image.putdata(new_data)
    
    # 如果需要应用纹理
    if apply_texture and fabric_type:
        return apply_fabric_texture(colored_image, fabric_type)
    
    return colored_image

def apply_text_to_shirt(image, text, color_hex="#FFFFFF", font_size=80):
    """Apply text to T-shirt image"""
    if not text:
        return image
    
    # 创建副本避免修改原图
    result_image = image.copy().convert("RGBA")
    img_width, img_height = result_image.size
    
    # 创建透明的文本图层
    text_layer = Image.new('RGBA', (img_width, img_height), (0, 0, 0, 0))
    text_draw = ImageDraw.Draw(text_layer)
    
    # 尝试加载字体
    from PIL import ImageFont
    import platform
    
    font = None
    try:
        system = platform.system()
        
        # 根据不同系统尝试不同的字体路径
        if system == 'Windows':
            font_paths = [
                "C:/Windows/Fonts/arial.ttf",
                "C:/Windows/Fonts/ARIAL.TTF",
                "C:/Windows/Fonts/calibri.ttf",
            ]
        elif system == 'Darwin':  # macOS
            font_paths = [
                "/Library/Fonts/Arial.ttf",
                "/System/Library/Fonts/Helvetica.ttc",
            ]
        else:  # Linux或其他
            font_paths = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
            ]
        
        # 尝试加载每个字体
        for font_path in font_paths:
            if os.path.exists(font_path):
                font = ImageFont.truetype(font_path, font_size)
                break
    except Exception as e:
        print(f"Error loading font: {e}")
    
    # 如果加载失败，使用默认字体
    if font is None:
        try:
            font = ImageFont.load_default()
        except:
            print("Could not load default font")
            return result_image
    
    # 将十六进制颜色转换为RGB
    color_rgb = tuple(int(color_hex.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
    text_color = color_rgb + (255,)  # 添加不透明度
    
    # 计算文本位置 (居中)
    text_bbox = text_draw.textbbox((0, 0), text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]
    
    text_x = (img_width - text_width) // 2
    text_y = (img_height // 3) - (text_height // 2)  # 放在T恤上部位置
    
    # 绘制文本
    text_draw.text((text_x, text_y), text, fill=text_color, font=font)
    
    # 组合图像
    result_image = Image.alpha_composite(result_image, text_layer)
    
    return result_image

def apply_logo_to_shirt(shirt_image, logo_image, position="center", size_percent=60, background_color=None):
    """Apply logo to T-shirt image with better blending to reduce shadows"""
    if logo_image is None:
        return shirt_image
    
    # 创建副本避免修改原图
    result_image = shirt_image.copy().convert("RGBA")
    img_width, img_height = result_image.size
    
    # 定义T恤前胸区域
    chest_width = int(img_width * 0.95)
    chest_height = int(img_height * 0.6)
    chest_left = (img_width - chest_width) // 2
    chest_top = int(img_height * 0.2)
    
    # 提取logo前景
    logo_with_bg = logo_image.copy().convert("RGBA")
    
    # 调整Logo大小
    logo_size_factor = size_percent / 100
    logo_width = int(chest_width * logo_size_factor * 0.7)
    logo_height = int(logo_width * logo_with_bg.height / logo_with_bg.width)
    logo_resized = logo_with_bg.resize((logo_width, logo_height), Image.LANCZOS)
    
    # 根据位置确定坐标
    position = position.lower() if isinstance(position, str) else "center"
    
    if position == "top-center":
        logo_x, logo_y = chest_left + (chest_width - logo_width) // 2, chest_top + 10
    elif position == "center":
        logo_x, logo_y = chest_left + (chest_width - logo_width) // 2, chest_top + (chest_height - logo_height) // 2 + 30  # 略微偏下
    else:  # 默认中间
        logo_x, logo_y = chest_left + (chest_width - logo_width) // 2, chest_top + (chest_height - logo_height) // 2 + 30
    
    # 创建一个蒙版，用于混合logo和T恤
    # 提取logo的非背景部分
    logo_mask = Image.new("L", logo_resized.size, 0)  # 创建一个黑色蒙版（透明）
    
    # 如果提供了背景颜色，使用它来判断什么是背景
    if background_color:
        bg_color_rgb = tuple(int(background_color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
    else:
        # 默认假设白色是背景
        bg_color_rgb = (255, 255, 255)
    
    # 遍历像素，创建蒙版
    for y in range(logo_resized.height):
        for x in range(logo_resized.width):
            pixel = logo_resized.getpixel((x, y))
            if len(pixel) >= 3:  # 至少有RGB值
                # 计算与背景颜色的差异
                r_diff = abs(pixel[0] - bg_color_rgb[0])
                g_diff = abs(pixel[1] - bg_color_rgb[1])
                b_diff = abs(pixel[2] - bg_color_rgb[2])
                diff = r_diff + g_diff + b_diff
                
                # 如果差异大于阈值，则认为是前景
                if diff > 60:  # 可以调整阈值
                    # 根据差异程度设置不同的透明度
                    transparency = min(255, diff)
                    logo_mask.putpixel((x, y), transparency)
    
    # 获取logo区域在T恤上的背景图像
    shirt_region = result_image.crop((logo_x, logo_y, logo_x + logo_width, logo_y + logo_height))
    
    # 合成logo和T恤区域，使用蒙版确保只有logo的非背景部分被使用
    # 这样能够保留T恤的原始纹理
    for y in range(logo_height):
        for x in range(logo_width):
            mask_value = logo_mask.getpixel((x, y))
            if mask_value > 20:  # 有一定的不透明度
                # 获取logo像素
                logo_pixel = logo_resized.getpixel((x, y))
                # 获取T恤对应位置的像素
                shirt_pixel = shirt_region.getpixel((x, y))
                
                # 根据透明度混合像素
                alpha = mask_value / 255.0
                blended_pixel = (
                    int(logo_pixel[0] * alpha + shirt_pixel[0] * (1 - alpha)),
                    int(logo_pixel[1] * alpha + shirt_pixel[1] * (1 - alpha)),
                    int(logo_pixel[2] * alpha + shirt_pixel[2] * (1 - alpha)),
                    255  # 完全不透明
                )
                
                # 更新T恤区域的像素
                shirt_region.putpixel((x, y), blended_pixel)
    
    # 将修改后的区域粘贴回T恤
    result_image.paste(shirt_region, (logo_x, logo_y))
    
    return result_image

def generate_complete_design(design_prompt, variation_id=None):
    """Generate complete T-shirt design based on prompt"""
    if not design_prompt:
        return None, {"error": "Please enter a design prompt"}
    
    # 获取AI设计建议
    design_suggestions = get_ai_design_suggestions(design_prompt)
    
    if "error" in design_suggestions:
        return None, design_suggestions
    
    # 加载原始T恤图像
    try:
        original_image_path = "white_shirt.png"
        possible_paths = [
            "white_shirt.png",
            "./white_shirt.png",
            "../white_shirt.png",
            "images/white_shirt.png",
        ]
        
        found = False
        for path in possible_paths:
            if os.path.exists(path):
                original_image_path = path
                found = True
                break
        
        if not found:
            return None, {"error": "Could not find base T-shirt image"}
        
        # 加载原始白色T恤图像
        original_image = Image.open(original_image_path).convert("RGBA")
    except Exception as e:
        return None, {"error": f"Error loading T-shirt image: {str(e)}"}
    
    try:
        # 使用AI建议的颜色和面料
        color_hex = design_suggestions.get("color", {}).get("hex", "#FFFFFF")
        color_name = design_suggestions.get("color", {}).get("name", "Custom Color")
        fabric_type = design_suggestions.get("fabric", "Cotton")
        
        # 1. 应用颜色和纹理
        colored_shirt = change_shirt_color(
            original_image,
            color_hex,
            apply_texture=True,
            fabric_type=fabric_type
        )
        
        # 2. 生成Logo
        logo_description = design_suggestions.get("logo", "")
        logo_image = None
        
        if logo_description:
            # 修改Logo提示词，明确指定颜色代码，确保生成的Logo背景与T恤颜色完全一致
            logo_prompt = f"""Create a Logo design for printing: {logo_description}. 
            Requirements: 
            1. Simple professional design
            2. IMPORTANT: The background MUST be exactly {color_name} color with HEX code {color_hex}
            3. Clear and distinct graphic
            4. Good contrast with colors that will show well on fabric
            5. Must remeber taht do not include any text, numbers or color name, only logo graphic
            6. IMPORTANT: Do NOT include any mockups or product previews
            7. IMPORTANT: Create ONLY the logo graphic itself
            8. NO META REFERENCES - do not show the logo applied to anything
            9. Design should be a standalone graphic symbol/icon only
            10. CRITICAL: The entire background must be solid color {color_hex} with no variations"""
            
            # 使用当前T恤颜色生成logo
            logo_image = generate_vector_image(logo_prompt, color_hex)
        
        # 最终设计 - 不添加文字
        final_design = colored_shirt
        
        # 应用Logo (如果有)
        if logo_image:
            # 使用与T恤相同的颜色作为logo背景
            final_design = apply_logo_to_shirt(colored_shirt, logo_image, "center", 60, color_hex)
        
        return final_design, {
            "color": {"hex": color_hex, "name": color_name},
            "fabric": fabric_type,
            "logo": logo_description,
            "design_index": 0 if variation_id is None else variation_id  # 使用design_index替代variation_id
        }
    
    except Exception as e:
        import traceback
        traceback_str = traceback.format_exc()
        return None, {"error": f"Error generating design: {str(e)}\n{traceback_str}"}

def generate_single_design(design_index):
    try:
        # 为每个设计添加轻微的提示词变化，确保设计多样性
        design_variations = [
            "",  # 原始提示词
            "modern and minimalist",
            "colorful and vibrant",
            "vintage and retro",
            "elegant and simple"
        ]
        
        # 选择合适的变化描述词
        variation_desc = ""
        if design_index < len(design_variations):
            variation_desc = design_variations[design_index]
        
        # 创建变化的提示词
        if variation_desc:
            # 将变化描述词添加到原始提示词
            varied_prompt = f"{design_prompt}, {variation_desc}"
        else:
            varied_prompt = design_prompt
        
        # 完整的独立流程 - 每个设计独立获取AI建议、生成图片，确保颜色一致性
        # 使用独立提示词生成完全不同的设计
        design, info = generate_complete_design(varied_prompt)
        
        # 添加设计索引到信息中以便排序
        if info and isinstance(info, dict):
            info["design_index"] = design_index
        
        return design, info
    except Exception as e:
        print(f"Error generating design {design_index}: {e}")
        return None, {"error": f"Failed to generate design {design_index}"}

def generate_multiple_designs(design_prompt, count=1):
    """Generate multiple T-shirt designs in parallel - independent designs rather than variations"""
    if count <= 1:
        # 如果只需要一个设计，直接生成不需要并行
        base_design, base_info = generate_complete_design(design_prompt)
        if base_design:
            return [(base_design, base_info)]
        else:
            return []
    
    designs = []
    
    # 创建线程池
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(count, 5)) as executor:
        # 提交所有任务
        future_to_id = {executor.submit(generate_single_design, i): i for i in range(count)}
        
        # 收集结果
        for future in concurrent.futures.as_completed(future_to_id):
            design_id = future_to_id[future]
            try:
                design, info = future.result()
                if design:
                    designs.append((design, info))
            except Exception as e:
                print(f"Design {design_id} generated an exception: {e}")
    
    # 按照设计索引排序
    designs.sort(key=lambda x: x[1].get("design_index", 0) if x[1] and "design_index" in x[1] else 0)
    
    return designs

def clear_all_cache():
    """完全清除所有缓存状态，确保每次都是全新的"""
    cache_keys = ['user_prompt', 'final_design', 'design_info', 'is_generating', 
                  'should_generate', 'generated_designs', 'selected_design_index', 'keywords']
    for key in cache_keys:
        if key in st.session_state:
            del st.session_state[key]

def show_high_recommendation_without_explanation():
    st.title("👕 AI Recommendation Experiment Platform")
    st.markdown("### Study1-Let AI Design Your T-shirt")
    
    # 在页面开始时清除所有缓存
    clear_all_cache()
    
    # 显示实验组和设计数量信息
    st.info(f"You are currently in Study1, and AI will generate {DEFAULT_DESIGN_COUNT} T-shirt design options for you")
    
    # 初始化会话状态变量
    if 'user_prompt' not in st.session_state:
        st.session_state.user_prompt = ""
    if 'final_design' not in st.session_state:
        st.session_state.final_design = None
    if 'design_info' not in st.session_state:
        st.session_state.design_info = None
    if 'is_generating' not in st.session_state:
        st.session_state.is_generating = False
    if 'should_generate' not in st.session_state:
        st.session_state.should_generate = False
    if 'recommendation_level' not in st.session_state:
        # 设置固定推荐级别，不再允许用户选择
        if DEFAULT_DESIGN_COUNT == 1:
            st.session_state.recommendation_level = "low"
        elif DEFAULT_DESIGN_COUNT == 3:
            st.session_state.recommendation_level = "medium"
        else:  # 5或其他值
            st.session_state.recommendation_level = "high"
    if 'generated_designs' not in st.session_state:
        st.session_state.generated_designs = []
    if 'selected_design_index' not in st.session_state:
        st.session_state.selected_design_index = 0
    if 'original_tshirt' not in st.session_state:
        # 加载原始白色T恤图像
        try:
            original_image_path = "white_shirt.png"
            possible_paths = [
                "white_shirt.png",
                "./white_shirt.png",
                "../white_shirt.png",
                "images/white_shirt.png",
            ]
            
            found = False
            for path in possible_paths:
                if os.path.exists(path):
                    original_image_path = path
                    found = True
                    break
            
            if found:
                st.session_state.original_tshirt = Image.open(original_image_path).convert("RGBA")
            else:
                st.error("Could not find base T-shirt image")
                st.session_state.original_tshirt = None
        except Exception as e:
            st.error(f"Error loading T-shirt image: {str(e)}")
            st.session_state.original_tshirt = None
    
    # 创建两列布局
    design_col, input_col = st.columns([3, 2])
    
    with design_col:
        # 创建占位区域用于T恤设计展示
        design_area = st.empty()
        
        # 在设计区域显示当前状态的T恤设计
        if st.session_state.final_design is not None:
            with design_area.container():
                st.markdown("### Your Custom T-shirt Design")
                st.image(st.session_state.final_design, use_container_width=True)
        elif len(st.session_state.generated_designs) > 0:
            with design_area.container():
                st.markdown("### Generated Design Options")
                
                # 创建多列来显示设计
                design_count = len(st.session_state.generated_designs)
                if design_count > 3:
                    # 两行显示
                    row1_cols = st.columns(min(3, design_count))
                    row2_cols = st.columns(min(3, max(0, design_count - 3)))
                    
                    # 显示第一行
                    for i in range(min(3, design_count)):
                        with row1_cols[i]:
                            design, _ = st.session_state.generated_designs[i]
                            st.markdown(f"<p style='text-align:center;'>Design {i+1}</p>", unsafe_allow_html=True)
                            # 显示设计
                            st.image(design, use_container_width=True)
                    
                    # 显示第二行
                    for i in range(3, design_count):
                        with row2_cols[i-3]:
                            design, _ = st.session_state.generated_designs[i]
                            st.markdown(f"<p style='text-align:center;'>Design {i+1}</p>", unsafe_allow_html=True)
                            # 显示设计
                            st.image(design, use_container_width=True)
                else:
                    # 单行显示
                    cols = st.columns(design_count)
                    for i in range(design_count):
                        with cols[i]:
                            design, _ = st.session_state.generated_designs[i]
                            st.markdown(f"<p style='text-align:center;'>Design {i+1}</p>", unsafe_allow_html=True)
                            # 显示设计
                            st.image(design, use_container_width=True)
                

        else:
            # 显示原始空白T恤
            with design_area.container():
                st.markdown("### T-shirt Design Preview")
                if st.session_state.original_tshirt is not None:
                    st.image(st.session_state.original_tshirt, use_container_width=True)
                else:
                    st.info("Could not load original T-shirt image, please refresh the page")
    
    with input_col:
        # 设计提示词和推荐级别选择区
        st.markdown("### Design Options")
        
        # # 移除推荐级别选择按钮，改为显示当前级别信息
        # if DEFAULT_DESIGN_COUNT == 1:
        #     level_text = "Low - will generate 1 design"
        # elif DEFAULT_DESIGN_COUNT == 3:
        #     level_text = "Medium - will generate 3 designs"
        # else:  # 5或其他值
        #     level_text = "High - will generate 5 designs"
            
        # st.markdown(f"""
        # <div style="padding: 10px; background-color: #f0f2f6; border-radius: 5px; margin-bottom: 20px;">
        # <p style="margin: 0; font-size: 16px; font-weight: bold;">Current recommendation level: {level_text}</p>
        # </div>
        # """, unsafe_allow_html=True)
        
        # 提示词输入区
        st.markdown("#### Describe your desired T-shirt design:")
        
        # 添加简短说明
        st.markdown("""
        <div style="margin-bottom: 15px; padding: 10px; background-color: #f0f2f6; border-radius: 5px;">
        <p style="margin: 0; font-size: 14px;">Enter three keywords to describe your ideal T-shirt design. 
        Our AI will combine these features to create unique designs for you.</p>
        </div>
        """, unsafe_allow_html=True)
        
        # 关键词输入框 - 不保存历史输入，每次都是空白
        keywords = st.text_input("Enter keywords for your design", value="", 
                              placeholder="e.g., casual, nature, blue", key="input_keywords")
        
        # 生成设计按钮
        generate_col = st.empty()
        with generate_col:
            generate_button = st.button("🎨 Generate T-shirt Design", key="generate_design", use_container_width=True)
        
        # 创建进度和消息区域在输入框下方
        progress_area = st.empty()
        message_area = st.empty()
        
        # 生成设计按钮事件处理
        if generate_button:
            # 不保存用户输入的关键词，确保每次都是全新输入
            
            # 检查是否输入了关键词
            if not keywords:
                st.error("Please enter at least one keyword")
            else:
                # 直接使用用户输入的关键词作为提示词
                user_prompt = keywords
                
                # 完全清除所有缓存状态，确保全新生成
                st.session_state.user_prompt = ""
                st.session_state.final_design = None
                st.session_state.generated_designs = []
                st.session_state.design_info = None
                st.session_state.selected_design_index = 0
                st.session_state.is_generating = False
                st.session_state.should_generate = False
                
                # 使用固定的设计数量
                design_count = DEFAULT_DESIGN_COUNT
                
                try:
                    # 显示生成进度
                    with design_area.container():
                        st.markdown("### Generating T-shirt Designs")
                        if st.session_state.original_tshirt is not None:
                            st.image(st.session_state.original_tshirt, use_container_width=True)
                    
                    # 创建进度条和状态消息在输入框下方
                    progress_bar = progress_area.progress(0)
                    message_area.info(f"AI is generating {design_count} unique designs for you. This may take about a minute. Please do not refresh the page or close the browser. Thank you for your patience! ♪(･ω･)ﾉ")
                    # 记录开始时间
                    start_time = time.time()
                    
                    # 收集生成的设计
                    designs = []
                    
                    # 生成单个设计的安全函数
                    def generate_single_safely(design_index):
                        try:
                            return generate_complete_design(user_prompt, design_index)
                        except Exception as e:
                            message_area.error(f"Error generating design: {str(e)}")
                            return None, {"error": f"Failed to generate design: {str(e)}"}
                    
                    # 对于单个设计，直接生成
                    if design_count == 1:
                        design, info = generate_single_safely(0)
                        if design:
                            designs.append((design, info))
                        progress_bar.progress(100)
                        message_area.success("Design generation complete!")
                    else:
                        # 为多个设计使用并行处理
                        completed_count = 0
                        
                        # 进度更新函数
                        def update_progress():
                            nonlocal completed_count
                            completed_count += 1
                            progress = int(100 * completed_count / design_count)
                            progress_bar.progress(progress)
                            message_area.info(f"Generated {completed_count}/{design_count} designs...")
                        
                        # 使用线程池并行生成多个设计
                        with concurrent.futures.ThreadPoolExecutor(max_workers=design_count) as executor:
                            # 提交所有任务
                            future_to_id = {executor.submit(generate_single_safely, i): i for i in range(design_count)}
                            
                            # 收集结果
                            for future in concurrent.futures.as_completed(future_to_id):
                                design_id = future_to_id[future]
                                try:
                                    design, info = future.result()
                                    if design:
                                        designs.append((design, info))
                                except Exception as e:
                                    message_area.error(f"Design {design_id} generation failed: {str(e)}")
                                
                                # 更新进度
                                update_progress()
                        
                        # 按照ID排序设计
                        designs.sort(key=lambda x: x[1].get("design_index", 0) if x[1] and "design_index" in x[1] else 0)
                    
                    # 记录结束时间
                    end_time = time.time()
                    generation_time = end_time - start_time
                    
                    # 存储生成的设计
                    if designs:
                        if design_count == 1:
                            # 对于单个设计，直接设为最终设计
                            st.session_state.final_design = designs[0][0]
                            st.session_state.design_info = designs[0][1]
                            st.session_state.generated_designs = []
                        else:
                            # 对于多个设计，显示选择选项
                            st.session_state.generated_designs = designs
                            st.session_state.selected_design_index = 0
                        message_area.success(f"Generated {len(designs)} designs in {generation_time:.1f} seconds!")
                    else:
                        message_area.error("Could not generate any designs. Please try again.")
                    
                    # 重新渲染设计区域以显示新生成的设计
                    st.rerun()
                except Exception as e:
                    import traceback
                    message_area.error(f"An error occurred: {str(e)}")
                    st.error(traceback.format_exc())
    

