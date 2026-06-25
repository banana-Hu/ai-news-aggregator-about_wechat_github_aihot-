"""
公众号文章正文提取工具。
从 mp.weixin.qq.com 页面下载 HTML 并提取纯文本正文。
优先使用 trafilatura，不可用时降级为正则提取。
"""

import logging
import re
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# 公众号文章 UA
MP_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# 文章请求超时
REQUEST_TIMEOUT = 15

# 最大 HTML 大小（10MB，防内存撑爆）
MAX_HTML_SIZE = 10 * 1024 * 1024

# 是否可用 trafilatura
_HAVE_TRAFILATURA = False
try:
    import trafilatura
    _HAVE_TRAFILATURA = True
except ImportError:
    logger.info("trafilatura 未安装，使用正则降级提取器")


def is_wechat_article(url: str) -> bool:
    """判断 URL 是否为公众号文章链接。"""
    return "mp.weixin.qq.com" in url.lower() and "/s/" in url


def extract_article_content(
    url: str,
    timeout: int = REQUEST_TIMEOUT,
    user_agent: str = MP_USER_AGENT,
) -> Optional[dict]:
    """下载并提取公众号文章正文。

    Args:
        url: 文章链接 (mp.weixin.qq.com/s/...)
        timeout: 请求超时秒数
        user_agent: 请求 UA

    Returns:
        dict 包含:
            title: 文章标题
            content_text: 纯文本正文
            content_html: 原始 HTML 正文区域
            author: 公众号名称
            cover_url: 封面图链接
            失败返回 None
    """
    if not is_wechat_article(url):
        logger.warning(f"非公众号文章链接: {url}")
        return None

    try:
        logger.info(f"下载文章: {url}")
        resp = requests.get(
            url,
            headers={"User-Agent": user_agent},
            timeout=timeout,
        )
        if resp.status_code != 200:
            logger.warning(f"下载失败 ({resp.status_code}): {url}")
            return None

        html = resp.text
        if len(html) > MAX_HTML_SIZE:
            logger.warning(f"HTML 过大 ({len(html)} bytes)，截断处理")
            html = html[:MAX_HTML_SIZE]

        logger.info(f"下载成功: {len(html)} bytes")

        # 提取元信息
        title = _extract_title(html)
        author = _extract_author(html)
        cover_url = _extract_cover_url(html)
        content_html = _extract_content_html(html)

        # 提取正文纯文本
        content_text = _extract_content_text(html, content_html)

        if not content_text and not content_html:
            logger.warning(f"未能提取到正文内容: {url}")
            return None

        # 截断过长内容
        if content_text and len(content_text) > 50000:
            content_text = content_text[:50000] + "\n\n... [TRUNCATED at 50K chars]"

        result = {
            "title": title or "",
            "content_text": content_text or "",
            "content_html": content_html or "",
            "author": author or "",
            "cover_url": cover_url or "",
        }
        logger.info(f"提取完成: title={result['title'][:40]}, text_len={len(result.get('content_text',''))}")
        return result

    except requests.exceptions.Timeout:
        logger.error(f"文章下载超时: {url}")
        return None
    except requests.exceptions.ConnectionError as e:
        logger.error(f"文章下载连接错误: {url}, {e}")
        return None
    except Exception as e:
        logger.error(f"文章提取异常: {url}, {e}", exc_info=True)
        return None


def _extract_title(html: str) -> Optional[str]:
    """从 HTML 提取文章标题。"""
    patterns = [
        r'<h1[^>]*class="rich_media_title[^"]*"[^>]*>(.*?)</h1>',
        r'<h2[^>]*class="rich_media_title[^"]*"[^>]*>(.*?)</h2>',
        r'var\s+msg_title\s*=\s*["\'](.*?)["\']',
        r'<title>(.*?)</title>',
        r'<meta[^>]*property="og:title"[^>]*content="(.*?)"[^>]*/?>',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
        if match:
            title = re.sub(r'<[^>]+>', '', match.group(1)).strip()
            if title:
                return title
    return None


def _extract_author(html: str) -> Optional[str]:
    """提取公众号名称。"""
    patterns = [
        r'var\s+msg_nickname\s*=\s*["\'](.*?)["\']',
        r'<strong[^>]*class="rich_media_meta_nickname[^"]*"[^>]*>(.*?)</strong>',
        r'<a[^>]*id="js_name"[^>]*>(.*?)</a>',
        r'<meta[^>]*property="og:article:author"[^>]*content="(.*?)"[^>]*/?>',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
        if match:
            author = re.sub(r'<[^>]+>', '', match.group(1)).strip()
            if author:
                return author
    return None


def _extract_cover_url(html: str) -> Optional[str]:
    """提取封面图链接。"""
    patterns = [
        r'var\s+msg_cdn_url\s*=\s*["\'](.*?)["\']',
        r'<meta[^>]*property="og:image"[^>]*content="(.*?)"[^>]*/?>',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            url = match.group(1).strip()
            if url:
                return url
    return None


def _extract_content_html(html: str) -> Optional[str]:
    """提取正文 HTML 区域。"""
    # 找 rich_media_content
    match = re.search(
        r'<div[^>]*id="js_content"[^>]*>(.*?)</div>\s*<script',
        html, re.DOTALL | re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()

    match = re.search(
        r'<div[^>]*class="rich_media_content[^"]*"[^>]*>(.*?)</div>\s*<(?:script|div)',
        html, re.DOTALL | re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()

    return None


def _extract_content_text(html: str, content_html: Optional[str] = None) -> Optional[str]:
    """提取正文纯文本。

    优先使用 trafilatura 提取，降级用正则。
    """
    if _HAVE_TRAFILATURA:
        try:
            import trafilatura
            text = trafilatura.extract(
                html,
                include_formatting=False,
                include_links=False,
                include_images=False,
                include_tables=False,
                no_fallback=False,
            )
            if text:
                return text.strip()
        except Exception as e:
            logger.debug(f"trafilatura 提取失败，降级正则: {e}")

    # 正则降级：从 content_html 或全文提取
    source_html = content_html or html

    # 移除 script / style
    source_html = re.sub(r'<script[^>]*>.*?</script>', '', source_html, flags=re.DOTALL)
    source_html = re.sub(r'<style[^>]*>.*?</style>', '', source_html, flags=re.DOTALL)

    # 提取纯文本
    text = re.sub(r'<[^>]+>', '\n', source_html)

    # 清理空白行
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    text = '\n'.join(lines)

    # 限制最小长度（纯导航/无内容页过滤）
    if len(text) < 50:
        return None

    return text


def extract_from_url(url: str, **kwargs) -> Optional[str]:
    """快捷函数：提取文章纯文本正文。"""
    result = extract_article_content(url, **kwargs)
    if result:
        return result.get("content_text")
    return None
