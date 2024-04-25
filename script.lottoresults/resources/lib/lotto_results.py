# lotto_results.py

import re

def extract_lotto_results(html_content):
    draw_number_pattern = r'<label id="ctl00_ContentPlaceHolder1_drawnumber">(\d+)</label>'
    draw_date_pattern = r'<label id="ctl00_ContentPlaceHolder1_drawdate">([^<]+)</label>'
    lotto_number_pattern = r'<img src="/lotto/balls/medium/(\d+)\.gif"'

    draw_number_match = re.search(draw_number_pattern, html_content)
    draw_number = draw_number_match.group(1) if draw_number_match else None

    draw_date_match = re.search(draw_date_pattern, html_content)
    draw_date = draw_date_match.group(1) if draw_date_match else None

    lotto_numbers = re.findall(lotto_number_pattern, html_content)

    return draw_number, draw_date, lotto_numbers
