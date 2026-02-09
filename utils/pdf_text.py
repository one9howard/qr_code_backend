"""
PDF Text Fitting Utilities

Shared primitives for text measurement, wrapping, and fitting in ReportLab PDFs.
Used by all sign renderers (yard signs, SmartSigns) for robust variable-length text handling.

Print Quality Rules:
- Never rasterize text - always draw as vector text objects
- Use registered fonts (from layout_utils.register_fonts)
- Clamp line counts per block type
"""
from reportlab.pdfbase.pdfmetrics import stringWidth
from typing import List, Tuple, Optional

# Max lines per block type
MAX_LINES_ADDRESS = 2
MAX_LINES_BROKERAGE = 1
MAX_LINES_CTA = 2
MAX_LINES_FEATURES = 1


def measure_text_width(text: str, font_name: str, font_size: float) -> float:
    """
    Measure text width in points using ReportLab's stringWidth.
    
    Args:
        text: Text to measure
        font_name: Registered font name
        font_size: Font size in points
        
    Returns:
        Width in points
    """
    if not text:
        return 0.0
    return stringWidth(str(text), font_name, font_size)


def fit_font_size_single_line(
    text: str,
    font_name: str,
    max_width_pts: float,
    max_font_size: float,
    min_font_size: float = 8.0,
    step: float = 1.0
) -> float:
    """
    Find the largest font size that fits text within max_width on a single line.
    
    Args:
        text: Text to fit
        font_name: Registered font name
        max_width_pts: Maximum width in points
        max_font_size: Starting (maximum) font size
        min_font_size: Minimum font size to clamp to
        step: Size decrement step
        
    Returns:
        The largest font size that fits, clamped to min_font_size if too long.
    """
    if not text:
        return max_font_size
    
    size = max_font_size
    while size > min_font_size:
        width = measure_text_width(text, font_name, size)
        if width <= max_width_pts:
            return size
        size -= step
    
    return min_font_size


def wrap_text(
    text: str,
    font_name: str,
    font_size: float,
    max_width_pts: float,
    max_lines: int = 2
) -> List[str]:
    """
    Wrap text to fit within max_width, returning a list of lines.
    
    Uses word-wrap by default. If a single word is too long, splits by character.
    Truncates with "..." if max_lines exceeded.
    
    Args:
        text: Text to wrap
        font_name: Registered font name
        font_size: Font size in points
        max_width_pts: Maximum width per line in points
        max_lines: Maximum number of lines (last line truncated if exceeded)
        
    Returns:
        List of wrapped lines
    """
    if not text:
        return []
    
    text = str(text).strip()
    words = text.split()
    
    if not words:
        return []
    
    lines = []
    current_line = ""
    
    for word in words:
        # Check if word itself is too wide
        word_width = measure_text_width(word, font_name, font_size)
        
        if word_width > max_width_pts:
            # Split long word by character
            if current_line:
                lines.append(current_line.strip())
                current_line = ""
            
            # Character-split the long word
            char_line = ""
            for char in word:
                test_line = char_line + char
                if measure_text_width(test_line, font_name, font_size) <= max_width_pts:
                    char_line = test_line
                else:
                    if char_line:
                        lines.append(char_line)
                    char_line = char
            if char_line:
                current_line = char_line + " "
            continue
        
        # Normal word-wrap logic
        test_line = current_line + word + " "
        test_width = measure_text_width(test_line.strip(), font_name, font_size)
        
        if test_width <= max_width_pts:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line.strip())
            current_line = word + " "
    
    # Add remaining text
    if current_line.strip():
        lines.append(current_line.strip())
    
    # Truncate if too many lines
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        # Add ellipsis to last line if it fits, otherwise truncate
        last_line = lines[-1]
        ellipsis = "..."
        while last_line and measure_text_width(last_line + ellipsis, font_name, font_size) > max_width_pts:
            last_line = last_line[:-1]
        lines[-1] = last_line + ellipsis
    
    return lines


def draw_fitted_block(
    c,
    text: str,
    x: float,
    y: float,
    w: float,
    h: float,
    font_name: str,
    max_font_size: float,
    min_font_size: float = 8.0,
    leading_ratio: float = 1.15,
    align: str = 'center',
    max_lines: int = 2,
    color: Optional[Tuple[float, float, float]] = None
) -> Tuple[float, List[str], float]:
    """
    Draw text fitted within a bounding box, auto-sizing and wrapping.
    
    Tries largest font that fits, wraps to max_lines, draws centered vertically.
    
    Args:
        c: ReportLab canvas
        text: Text to draw
        x, y: Bottom-left corner of bounding box
        w, h: Width and height of bounding box
        font_name: Registered font name
        max_font_size: Starting font size
        min_font_size: Minimum font size
        leading_ratio: Line height multiplier
        align: 'left', 'center', or 'right'
        max_lines: Maximum lines allowed
        color: Optional RGB tuple (0-1 range)
        
    Returns:
        (used_font_size, lines_drawn, total_height_used)
    """
    if not text:
        return (max_font_size, [], 0)
    
    text = str(text).strip()
    
    # Binary search for best font size that fits
    best_size = min_font_size
    best_lines = wrap_text(text, font_name, min_font_size, w, max_lines)
    
    for size in range(int(max_font_size), int(min_font_size) - 1, -1):
        lines = wrap_text(text, font_name, float(size), w, max_lines)
        leading = size * leading_ratio
        total_height = len(lines) * leading
        
        if total_height <= h:
            # Check all lines fit width
            all_fit = all(
                measure_text_width(line, font_name, float(size)) <= w
                for line in lines
            )
            if all_fit:
                best_size = float(size)
                best_lines = lines
                break
    
    # Calculate vertical centering
    leading = best_size * leading_ratio
    total_text_height = len(best_lines) * leading
    y_start = y + (h + total_text_height) / 2 - best_size * 0.2  # Adjust for baseline
    
    # Draw lines
    if color:
        c.setFillColorRGB(*color)
    c.setFont(font_name, best_size)
    
    for i, line in enumerate(best_lines):
        line_y = y_start - (i * leading)
        line_width = measure_text_width(line, font_name, best_size)
        
        if align == 'center':
            line_x = x + (w - line_width) / 2
        elif align == 'right':
            line_x = x + w - line_width
        else:  # left
            line_x = x
        
        c.drawString(line_x, line_y, line)
    
    return (best_size, best_lines, total_text_height)


def draw_single_line_fitted(
    c,
    text: str,
    x: float,
    y: float,
    max_width: float,
    font_name: str,
    max_font_size: float,
    min_font_size: float = 8.0,
    align: str = 'center',
    color: Optional[Tuple[float, float, float]] = None
) -> float:
    """
    Draw text on a single line, shrinking font if needed.
    
    Args:
        c: ReportLab canvas
        text: Text to draw
        x, y: Position (varies by align: left=left edge, center=center, right=right edge)
        max_width: Maximum width in points
        font_name: Registered font name
        max_font_size: Starting font size
        min_font_size: Minimum font size
        align: 'left', 'center', or 'right'
        color: Optional RGB tuple (0-1 range)
        
    Returns:
        Font size used
    """
    if not text:
        return max_font_size
    
    text = str(text).strip()
    font_size = fit_font_size_single_line(text, font_name, max_width, max_font_size, min_font_size)
    
    if color:
        c.setFillColorRGB(*color)
    c.setFont(font_name, font_size)
    
    text_width = measure_text_width(text, font_name, font_size)
    
    if align == 'center':
        draw_x = x - text_width / 2
    elif align == 'right':
        draw_x = x - text_width
    else:  # left
        draw_x = x
    
    c.drawString(draw_x, y, text)
    return font_size


def format_features_line(beds, baths, sqft, separator: str = " | ") -> str:
    """
    Format beds/baths/sqft into a single line, omitting missing values gracefully.
    
    Args:
        beds: Bedroom count or None
        baths: Bathroom count or None  
        sqft: Square footage or None
        separator: String to join parts
        
    Returns:
        Formatted string (e.g., "4 Bed | 3 Bath | 2,500 sqft")
    """
    parts = []
    
    if beds is not None and str(beds).strip():
        try:
            beds_val = int(float(str(beds).strip()))
            parts.append(f"{beds_val} Bed")
        except (ValueError, TypeError):
            pass
    
    if baths is not None and str(baths).strip():
        try:
            baths_str = str(baths).strip()
            baths_val = float(baths_str)
            if baths_val == int(baths_val):
                parts.append(f"{int(baths_val)} Bath")
            else:
                parts.append(f"{baths_val} Bath")
        except (ValueError, TypeError):
            pass
    
    if sqft is not None and str(sqft).strip():
        try:
            sqft_val = int(float(str(sqft).strip().replace(',', '')))
            parts.append(f"{sqft_val:,} sqft")
        except (ValueError, TypeError):
            pass
    
    return separator.join(parts)
