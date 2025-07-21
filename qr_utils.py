import qrcode

def generate_qr_code(link, output_path="static/qr_code.png"):
    img = qrcode.make(link)
    img.save(output_path)
