import math
from pathlib import Path
from PIL import Image, ImageDraw

def create_gradient_icon(size=256, corner_radius=68):
    # Create image with transparent background (RGBA)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    
    # Generate gradient background
    # Colors: #06B6D4 (6, 182, 212) -> #3B82F6 (59, 130, 246) -> #8B5CF6 (139, 92, 246)
    c1 = (6, 182, 212)
    c2 = (59, 130, 246)
    c3 = (139, 92, 246)
    
    # We will draw super-sampled for ultra-smooth anti-aliasing
    scale = 4
    large_size = size * scale
    large_radius = corner_radius * scale
    
    # Create large mask and gradient
    mask = Image.new("L", (large_size, large_size), 0)
    draw_mask = ImageDraw.Draw(mask)
    margin = 8 * scale
    draw_mask.rounded_rectangle(
        [margin, margin, large_size - margin, large_size - margin],
        radius=large_radius,
        fill=255
    )
    
    gradient_img = Image.new("RGBA", (large_size, large_size), (0, 0, 0, 0))
    grad_draw = ImageDraw.Draw(gradient_img)
    
    for y in range(large_size):
        for x in range(large_size):
            t = (x + y) / (2.0 * large_size)
            if t < 0.5:
                sub_t = t * 2.0
                r = int(c1[0] + (c2[0] - c1[0]) * sub_t)
                g = int(c1[1] + (c2[1] - c1[1]) * sub_t)
                b = int(c1[2] + (c2[2] - c1[2]) * sub_t)
            else:
                sub_t = (t - 0.5) * 2.0
                r = int(c2[0] + (c3[0] - c2[0]) * sub_t)
                g = int(c2[1] + (c3[1] - c2[1]) * sub_t)
                b = int(c2[2] + (c3[2] - c2[2]) * sub_t)
            gradient_img.putpixel((x, y), (r, g, b, 255))
            
    # Apply rounded mask to gradient
    gradient_img.putalpha(mask)
    
    # Draw Camera on top
    cam_draw = ImageDraw.Draw(gradient_img)
    
    # Camera coordinates centered in large_size
    # 24x24 standard SVG camera scaled to fit beautifully
    cx, cy = large_size // 2, large_size // 2
    cam_w = int(120 * scale)
    cam_h = int(90 * scale)
    stroke_w = int(9 * scale)
    
    # Main camera body box
    bx0 = cx - cam_w // 2
    by0 = cy - cam_h // 2 + int(12 * scale)
    bx1 = cx + cam_w // 2
    by1 = cy + cam_h // 2 + int(12 * scale)
    cam_draw.rounded_rectangle([bx0, by0, bx1, by1], radius=int(18 * scale), outline=(255, 255, 255, 255), width=stroke_w)
    
    # Top flash / bump
    top_w = int(45 * scale)
    top_h = int(18 * scale)
    tx0 = cx - top_w // 2
    ty0 = by0 - top_h
    cam_draw.rounded_rectangle([tx0, ty0, tx0 + top_w, by0 + stroke_w], radius=int(6 * scale), fill=(255, 255, 255, 255))
    
    # Center lens circle
    lens_r = int(32 * scale)
    lens_cy = (by0 + by1) // 2
    cam_draw.ellipse([cx - lens_r, lens_cy - lens_r, cx + lens_r, lens_cy + lens_r], outline=(255, 255, 255, 255), width=stroke_w)
    
    # Small top-right lens dot / flash indicator
    dot_r = int(5 * scale)
    cam_draw.ellipse([bx1 - int(24 * scale) - dot_r, by0 + int(18 * scale) - dot_r, bx1 - int(24 * scale) + dot_r, by0 + int(18 * scale) + dot_r], fill=(255, 255, 255, 255))

    # Downsample with Lanczos for perfect anti-aliasing
    final_img = gradient_img.resize((size, size), Image.Resampling.LANCZOS)
    return final_img

if __name__ == "__main__":
    icon_256 = create_gradient_icon(256, 64)
    
    targets = [
        Path("web_demo/favicon.png"),
        Path("favicon.png"),
    ]
    for target in targets:
        icon_256.save(target, format="PNG")
        print(f"Saved {target}")
        
    # Save multi-res ICO
    ico_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    ico_imgs = [icon_256.resize(s, Image.Resampling.LANCZOS) for s in ico_sizes]
    
    for ico_path in [Path("web_demo/favicon.ico"), Path("favicon.ico")]:
        ico_imgs[0].save(ico_path, format="ICO", sizes=ico_sizes, append_images=ico_imgs[1:])
        print(f"Saved {ico_path}")
