import numpy as np
import pdfplumber
from table_finder import TableFinder

class LayoutExtractor:
    def __init__(self, table) -> None:
        self.table = table

    def find_columns(self):
        pass

    def find_rows(self):
        pass

    def layout(self):
        pass

if __name__ == '__main__':

    with pdfplumber.open("examples/pdf/FDX/2017/page_26.pdf") as pdf:
        page = pdf.pages[0]
        t_finder = TableFinder(page)
        tables = t_finder.find_tables()
        table_crop = page.crop(tables[0]['bbox'])
        
        table_settings = {
            "vertical_strategy": "text",
            "horizontal_strategy": "lines",
            "snap_x_tolerance": 0,
            "text_x_tolerance": 0,
            "explicit_vertical_lines": [tables[0]['bbox'][0], tables[0]['bbox'][2]],
            "explicit_horizontal_lines": [tables[0]['bbox'][1], tables[0]['bbox'][3]]
        }

        t = table_crop.extract_tables(table_settings)
        for i in t[0]:
            print(i)
            print()
        im = table_crop.to_image(resolution=300)
        im.debug_tablefinder(table_settings)
        #im.draw_lines(tables[0]['lines'])
        im.save('table.png')