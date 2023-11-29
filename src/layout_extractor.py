import numpy as np
import pdfplumber
from table_finder import TableFinder
import copy
class LayoutExtractor:
    def __init__(self, table, clipping) -> None:
        self.table = table
        self.clipping = clipping

    def find_columns(self, max_diff, special_symbols):
        chars = sorted(self.clipping.chars, key=lambda e: e['x0'])
        separator = []
        i=0
        while i < len(chars)-1:
            char = chars[i+1]
            # remove white spaces
            if char['text'] == ' ':
                chars.pop(i+1)
            else:
                diff = char['x0'] - chars[i]['x1']
                # set a new column separator if the horizontal distance between two characters is greater then max_diff or if the font changes
                # some tables have header lines with another font too --> so the font change is only considered a column divider, 
                # if the distance to the next character is greater than 1
                if diff > max_diff or (diff > 1 and char['fontname'] != chars[i]['fontname']):
                    top, bottom = self.table['bbox'][1], self.table['footer']
                    separator.append({'x0': char['x0'], 'top': top, 'x1': char['x0'], 'bottom': bottom, 'object_type': 'line', 'height': bottom-top})
                if chars[0]['text'] in special_symbols or char['text'] in special_symbols:
                    top, bottom = self.find_unit_column(char)
                    separator.append({'x0': char['x0'], 'top': top, 'x1': char['x0'], 'bottom': bottom, 'object_type': 'line', 'height': bottom-top})
                    separator.append({'x0': char['x1'], 'top': top, 'x1': char['x1'], 'bottom': bottom, 'object_type': 'line', 'height': bottom-top})

                i+=1

        return separator

    def find_rows(self, max_diff):
        chars = sorted(self.clipping.chars, key=lambda e: e['top'])
        separator = []
        footnote_complete = None
        footnote_separator = []

        i=0
        while i < len(chars)-1:
            # remove white spaces
            if chars[i+1]['text'] == " ":
                chars.pop(i+1)
            else:
                diff = chars[i+1]['top'] - chars[i]['bottom']
                if diff > max_diff:
                    avg = (chars[i]['bottom'] + chars[i+1]['top']) / 2
                    footnote_separator.append(avg) if footnote_complete else separator.append(avg)

                # separate footer
                if chars[i+1]['size'] != chars[i]['size']: # possible footnote
                    if diff < 0: 
                        self.table['footer'] = self.table['bbox'][3]
                        footnote_complete = False
                    else: 
                        self.table['footer'] = chars[i]['bottom']
                        separator.extend(footnote_separator)
                        footnote_complete = True
                    #footnote_complete = not footnote_complete
                
                i+=1

        if footnote_complete == None: 
            separator.extend(footnote_separator)
            footnote_complete = True

        bbox = copy.copy(self.table['bbox'])
        bbox[3] = self.table['footer']
        self.clipping = self.clipping.crop(bbox)

        return footnote_complete, separator
    
    def find_unit_column(self, char):
        lines = sorted(self.table['lines'], key=lambda e: e['top'])
        lines.append({'top': self.table['footer'], 'bottom': self.table['footer']})

        for i in range(len(lines)-1):
            if char['top'] >= lines[i]['bottom'] and char['bottom'] <= lines[i+1]['top']:
                return lines[i]['bottom'], lines[i+1]['top']
            
        return self.table['bbox'][1], self.table['footer']

    def find_cells(self):
        vertical_lines = [self.table['bbox'][0], self.table['bbox'][2]] # left and right line
        horizontal_lines = [self.table['header'], self.table['footer']] # top and bottom line
        if "column_separator" in vars(self).keys():
            vertical_lines.extend(self.column_separator)
        if "row_separator" in vars(self).keys():
            horizontal_lines.extend(self.row_separator)

        table_settings = {
            "vertical_strategy": "explicit",
            "horizontal_strategy": "explicit",
            "snap_tolerance": 3,
            "text_tolerance": 0,
            "intersection_tolerance": 0,
            "join_tolerance": 0,
            "min_words_vertical": 0,
            "min_words_horizontal": 0,
            "explicit_vertical_lines": vertical_lines,
            "explicit_horizontal_lines": horizontal_lines
        }

        t = table_clip.extract_tables(table_settings)

        return table_settings

    def find_layout(self, x_space, y_space, symbols):
        footnote_complete, self.row_separator = self.find_rows(y_space)

        if not footnote_complete: return footnote_complete, 0, 0

        self.column_separator = self.find_columns(x_space, symbols)

        return footnote_complete, self.column_separator, self.row_separator


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
    path = "examples/pdf/FDX/2017/page_83.pdf"
    footnote_complete = False
    threshold = 5 # max_diff for finding table bottom

    while not footnote_complete or threshold < 20: # increase threshold if the footnote is incomplete -> try again to find the table
        with pdfplumber.open(path) as pdf:
            page = pdf.pages[0]
            t_finder = TableFinder(page)
            tables = t_finder.find_tables(bottom_threshold=threshold)
            table_clip = page.crop(tables[0]['bbox'])

        threshold += 5

        le = LayoutExtractor(tables[0], table_clip)
        footnote_complete, column_separator, row_separator = le.find_layout(5, 2, ['$', '%']) # first value to 3 for separating dollar signs and to 0.01 for separating also percent signs
        
    im = table_clip.to_image(resolution=300)
    im.draw_lines(tables[0]['lines'], stroke_width=3, stroke=(0,0,0))
    #im.draw_hline(tables[0]['footer'], stroke_width=3, stroke=(200,0,0))
    #im.draw_lines(column_separator, stroke_width=2)
    #im.draw_hlines(row_separator, stroke_width=2)

    t = le.find_cells()

    im.debug_tablefinder(t)
    table = table_clip.extract_table(t)
    
    im.save('table.png')

    import pandas as pd
    df = pd.DataFrame(table[1:], columns=table[0])
    df.to_excel("test.xlsx")

    #pdfplumber_table_extraction(tables[0], table_clip)