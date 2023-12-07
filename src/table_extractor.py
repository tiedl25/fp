import pandas as pd
import pdfplumber
import copy

from .table_finder import TableFinder
from .layout_extractor import LayoutExtractor

class TableExtractor:
    def __init__(self, path, separate_units=False):
        self.path = path
        pdf = pdfplumber.open(path)
        self.pages = pdf.pages
        self.separate_units = separate_units

    def tableToDataframe(self, table):
        '''
            Create a dataframe from table cells. Header cells with none type are merged with the next column.
        '''
        tuples = []
        i=0
        header = table[0]
        while i < len(header):
            if header[i] != None and (i+1 == len(header) or header[i+1] != None):
                tuples.append((header[i], ''))
            elif header[i] != None:
                tuples.extend([(header[i], ''), (header[i], '')])
                header.pop(i+1)
            i+=1
    
        columns = pd.MultiIndex.from_tuples(tuples)

        return pd.DataFrame(table[1:], columns=columns)
    
    def export(self, format, path, dataframe=None, table=None):
        if dataframe is None:
            if table is None:
                return
            dataframe = self.tableToDataframe(table)

        if format == 'excel':
            return dataframe.to_excel(f'{path}.xlsx')    
        elif format == 'csv':
            return dataframe.to_latex(f'{path}.csv', index=False)      

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
            le = LayoutExtractor(table, table_clip, separate_units=self.separate_units)
            footnote_complete, _, _ = le.find_layout(5, 2, ['$', '%'])

            threshold += 5

        if not footnote_complete:
            return None
        
        table_settings = le.find_cells()
        plumber_table = table_clip.find_table(table_settings)
        table['settings'] = table_settings
        table['cells'] = plumber_table.cells
        table['text'] = plumber_table.extract(x_tolerance=2)

        modified_list_of_lists = [
            [s.replace('\n', ' ') for s in inner_list]
            for inner_list in table['text']
        ]

        table['text'] = modified_list_of_lists

        if img_path != None:
            im = table_clip.to_image(resolution=300)
            im.draw_lines(table['lines'], stroke_width=3, stroke=(0,0,0)) # redraw existing lines
            im.debug_tablefinder(table_settings)
            im.save(img_path)

        return table

    def extractTables(self, page_index=None, img_path=None):
        ''' 
            Extract multiple tables.
        '''
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
    te = TableExtractor(path="examples/pdf/FDX/2017/page_36.pdf", separate_units=False)
    tables = te.extractTables(page_index=0, img_path='table.png')
    
    dataframes = [te.tableToDataframe(table['text']) for table in tables]
    for i, df in enumerate(dataframes): te.export('excel', f'excel/test_{i}', dataframe=df)