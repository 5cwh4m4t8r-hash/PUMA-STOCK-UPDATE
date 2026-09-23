from PIL import Image, ImageDraw

S = 512
im = Image.new("RGBA", (S, S), (6, 18, 31, 255))
d = ImageDraw.Draw(im)

# rounded dark card + gold border
d.rounded_rectangle((14, 14, 498, 498), radius=92, fill=(7, 27, 46, 255), outline=(232, 173, 55, 255), width=10)

# stylized puma head
head = [
    (78, 292), (105, 218), (151, 150), (215, 103), (286, 79),
    (260, 119), (244, 161), (287, 136), (334, 127), (382, 141),
    (343, 158), (318, 184), (305, 203), (341, 202), (382, 223),
    (341, 230), (314, 246), (291, 275), (257, 307), (208, 327),
    (158, 334), (112, 316)
]
d.polygon(head, fill=(16, 28, 41, 255))
d.line(head + [head[0]], fill=(235, 180, 60, 255), width=8, joint="curve")

# eye
d.polygon([(165, 220), (197, 199), (246, 205), (216, 225), (200, 245), (179, 239)], fill=(0, 161, 255, 255))
d.ellipse((198, 211, 214, 227), fill=(239, 252, 255, 255))

# rising chart
blue=(45, 203, 255, 255)
gold=(240, 183, 57, 255)
pts=[(282, 368),(325, 327),(351, 348),(395, 291),(438, 311)]
d.line(pts, fill=blue, width=15, joint="curve")
d.line([(414,268),(449,289),(429,329)], fill=gold, width=14, joint="curve")
for x,y in [(301,370),(335,350),(369,330),(402,309)]:
    d.line((x,y,x,408), fill=gold, width=8)

# compact P mark
d.rounded_rectangle((160, 420, 352, 470), radius=18, outline=gold, width=4)
d.text((205, 427), "PUMA", fill=gold)

png="launcher/PUMA_STOCK_PRO.png"
ico="launcher/PUMA_STOCK_PRO.ico"
im.save(png)
im.save(ico, format="ICO", sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
print("ICON OK")
