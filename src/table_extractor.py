import pandas as pd
import pdfplumber
import copy

from table_finder import TableFinder
from layout_extractor import LayoutExtractor

class TableExtractor:
    def __init__(self, path):
        self.path = path
        pdf = pdfplumber.open(path)
        self.pages = pdf.pages

    def tableToDataframe(self, table):
        tuples = []
        i=0
        header = table[0]
        while i < len(header)-1:
            if header[i] != None and header[i+1] != None:
                tuples.append((header[i], ''))
            elif header[i] != None:
                tuples.extend([(header[i], ''), (header[i], '')])
                header.pop(i+1)
            i+=1
    
        columns = pd.MultiIndex.from_tuples(tuples)

        return pd.DataFrame(table[1:], columns=columns)

    def extractTable(self, page, table_index=0, table=None, img_path=None):
        '''
            Use pdfplumbers table extraction method with custom settings. 
            The bounding box is retrieved with the TableFinder class and the columns and rows with the LayoutExtractor class.
            Those columns/rows can be specified as explicit lines in the table_settings and are then used to extract the cells.
        '''
        footnote_complete = False
        threshold = 5 # max_diff for finding table bottom
        
        while not footnote_complete and threshold < 20: # increase threshold if the footnote is incomplete -> try again to find the table
            
            # get table bbox if none is provided or a it does not include a correct footnote
            if table == None or threshold > 5:
                page = copy.copy(self.pages[0])
                tf = TableFinder(page)
                table = tf.find_tables(bottom_threshold=threshold)[table_index]

            table_clip = page.crop(table['bbox'])
            le = LayoutExtractor(table, table_clip)
            footnote_complete, _, _ = le.find_layout(5, 2, ['$', '%'])

            threshold += 5

        if not footnote_complete:
            return None
        
        table_settings = le.find_cells()

        if img_path != None:
            im = table_clip.to_image(resolution=300)
            im.draw_lines(table['lines'], stroke_width=3, stroke=(0,0,0)) # redraw existing lines
            im.debug_tablefinder(table_settings)
            im.save(img_path)

        table['settings'] = table_settings
        table['cells'] = table_clip.extract_table(table_settings)
        return table

    def extractTables(self, page_index=None, img_path=None):
        tables = []
        if page_index != None:
            page = copy.copy(self.pages[page_index])
            tf = TableFinder(page)

            if img_path != None:
                im = page.to_image(resolution=300)

            for table_index, tablebox in enumerate(tf.find_tables()):
                table = self.extractTable(page, table_index=table_index, table=tablebox)
                if table != None: 
                    tables.append(table)
                    if img_path != None:
                        im.draw_lines(table['lines'], stroke_width=3, stroke=(0,0,0)) # redraw existing lines
                        im.debug_tablefinder(table['settings'])
                        im.save(img_path)

            return tables

        for i in range(len(self.pages)):
            page = copy.copy(self.pages[i])
            tf = TableFinder(page)

            if img_path != None:
                im = page.to_image(resolution=300)

            for table_index, tablebox in enumerate(tf.find_tables()):
                table = self.extractTable(page, table_index=table_index, table=tablebox)
                if table != None: 
                    tables.append(table)
                    if img_path != None:
                        im.draw_lines(table['lines'], stroke_width=3, stroke=(0,0,0)) # redraw existing lines
                        im.debug_tablefinder(table['settings'])
                        im.save(f'{img_path}_{i})')
        
        return tables


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
    te = TableExtractor(path="examples/pdf/FDX/2017/page_83.pdf")
    tables = te.extractTables(page_index=0, img_path='table.png')
    dataframe = te.tableToDataframe(tables[0])
    #dataframes = [te.tableToDataframe(table) for table in tables]
    print(dataframe)