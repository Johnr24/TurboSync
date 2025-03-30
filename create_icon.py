#!/usr/bin/env python3

from PIL import Image, ImageDraw
import os

# Create a 512x512 icon
size = 512
image = Image.new('RGBA', (size, size), color=(255, 255, 255, 0))
draw = ImageDraw.Draw(image)

# Rainbow colors for pride flag
rainbow_colors = [
    (228, 3, 3),    # Red
    (255, 140, 0),  # Orange
    (255, 237, 0),  # Yellow
    (0, 128, 38),   # Green
    (0, 77, 255),   # Blue
    (117, 7, 135)   # Purple
]

# Create a base image for the stripes
stripes_img = Image.new('RGBA', (size, size), color=(255, 255, 255, 0))
stripes_draw = ImageDraw.Draw(stripes_img)

# Draw rainbow stripes (all rectangular without rounded corners)
margin = 50
stripe_height = (size - 2 * margin) // len(rainbow_colors)

for i, color in enumerate(rainbow_colors):
    y1 = margin + i * stripe_height
    y2 = y1 + stripe_height
    stripes_draw.rectangle(
        [(margin, y1), (size - margin, y2)],
        fill=color
    )

# Create a rounded rectangle mask
mask = Image.new('L', (size, size), 0)
mask_draw = ImageDraw.Draw(mask)
mask_draw.rounded_rectangle(
    [(margin, margin), (size - margin, size - margin)],
    fill=255,
    radius=60
)

# Apply the mask to the stripes
image.paste(stripes_img, (0, 0), mask)

# Draw a white "T" for TurboSync
draw = ImageDraw.Draw(image)
draw.rectangle(
    [(size // 2 - 30, margin + 80), (size // 2 + 30, size - margin - 80)],
    fill=(255, 255, 255)
)
draw.rectangle(
    [(size // 2 - 100, margin + 80), (size // 2 + 100, margin + 150)],
    fill=(255, 255, 255)
)

# Save as PNG
icon_dir = os.path.join('turbo_sync')
os.makedirs(icon_dir, exist_ok=True)
icon_path = os.path.join(icon_dir, 'icon.png')
image.save(icon_path)

print(f"Created icon at {icon_path}") 