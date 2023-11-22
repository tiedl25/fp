import numpy as np
import pdfplumber
from table_finder import TableFinder

class LayoutExtractor:
    def __init__(self, table, clipping) -> None:
        self.table = table
        self.clipping = clipping

    def find_columns(self, max_diff, symbols):
        chars = sorted(self.clipping.chars, key=lambda e: e['x0'])
        separator = []
        symbol_separator = []
        i=0
        while i < len(chars)-1:
            # remove white spaces
            if chars[i+1]['text'] == ' ':
                chars.pop(i+1)
            else:
                diff = chars[i+1]['x0'] - chars[i]['x1']
                if diff > max_diff:
                    separator.append(chars[i+1]['x0'])
                elif chars[i+1]['text'] in symbols or chars[i]['text'] in symbols:
                    symbol_separator.append(chars[i+1]['x0'])
                i+=1

        return separator        

    def find_rows(self, max_diff):
        chars = sorted(self.clipping.chars, key=lambda e: e['top'])
        separator = []
        i=0
        while i < len(chars)-1:
            # remove white spaces
            if chars[i+1]['text'] == ' ':
                chars.pop(i+1)
            else:
                diff = chars[i+1]['top'] - chars[i]['bottom']
                if diff > max_diff:
                    avg = (chars[i]['bottom'] + chars[i+1]['top']) / 2
                    separator.append(avg)

                i+=1

        return separator  

    def find_layout(self, x_space, y_space, symbols):
        column_separator = self.find_columns(x_space, symbols)
        row_separator = self.find_rows(y_space)

        return column_separator, row_separator


def pdfplumber_table_extraction(table, table_clip):
    table_settings = {
        "vertical_strategy": "text",
        "horizontal_strategy": "text",
        "snap_y_tolerance": 5,
        "snap_x_tolerance": 20,
        "text_x_tolerance": 20,
        "min_words_vertical": 0,
        "min_words_horizontal": 1,
        "explicit_vertical_lines": [table['bbox'][0], table['bbox'][2]],
        "explicit_horizontal_lines": [table['bbox'][1], table['bbox'][3]]
    }

    t = table_clip.extract_tables(table_settings)
    for i in t[0]:
        print(i)
        print()

        
    im = table_clip.to_image(resolution=300)
    im.debug_tablefinder(table_settings)
    #im.draw_lines(tables[0]['lines'])
    im.save('table.png')

    

if __name__ == '__main__':

    with pdfplumber.open("examples/pdf/FDX/2017/page_62.pdf") as pdf:
        page = pdf.pages[0]
        t_finder = TableFinder(page)
        tables = t_finder.find_tables()
        table_clip = page.crop(tables[0]['bbox'])

    le = LayoutExtractor(tables[0], table_clip)
    column_separator, row_separator = le.find_layout(5, 2, ['$', '%']) # first value to 3 for separating dollar signs and to 0.01 for separating also percent signs
    im = table_clip.to_image(resolution=300)
    im.draw_vlines(column_separator, stroke_width=2)
    im.draw_hlines(row_separator, stroke_width=2)
    im.save('table.png')

    #pdfplumber_table_extraction(tables[0], table_clip)       