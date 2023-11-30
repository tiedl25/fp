import pandas as pd
import pdfplumber

from table_finder import TableFinder
from layout_extractor import LayoutExtractor

def pdfplumber_table_extraction(table):
    '''
        pdfplumbers table extraction method with custom settings -> not working
    '''
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

    return table_settings

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
        footnote_complete, column_separator, row_separator = le.find_layout(5, 2, ['$', '%'])
        
    im = table_clip.to_image(resolution=300)
    im.draw_lines(tables[0]['lines'], stroke_width=3, stroke=(0,0,0))

    table_settings = le.find_cells()
    #table_settings = pdfplumber_table_extraction(tables[0], table_clip)

    im.debug_tablefinder(table_settings)
    table = table_clip.extract_table(table_settings)
    
    im.save('table.png')

    df = pd.DataFrame(table[1:], columns=table[0])
    df.to_excel("test.xlsx", index=False)
    print(df)

    