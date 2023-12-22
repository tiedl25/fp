import pandas as pd
import pdfplumber
import copy
from ultralyticsplus import YOLO, render_result

if __name__ == '__main__':  
    from table_finder import TableFinder
    from layout_extractor import LayoutExtractor
else:
    from .table_finder import TableFinder
    from .layout_extractor import LayoutExtractor

class TableExtractor:
    def __init__(self, path, separate_units=False, find_method='rule-based'):
        self.path = path
        pdf = pdfplumber.open(path)
        self.pages = pdf.pages
        self.separate_units = separate_units
        self.find_method = find_method

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
        if self.find_method == 'rule-based':
            footnote_complete = False
            threshold = 5 # max_diff for finding table bottom
            
            while not footnote_complete and threshold < 20: # increase threshold if the footnote is incomplete -> try again to find the table
                
                # get table bbox if none is provided or a it does not include a correct footnote
                if table == None or threshold > 5:
                    page = copy.copy(self.pages[0])
                    tf = TableFinder(page)
                    tables = tf.find_tables(bottom_threshold=threshold)

                    if table_index >= len(tables):
                        return None
                    table = tables[table_index]

                table_clip = page.crop(table['bbox'])
                le = LayoutExtractor(table, table_clip, separate_units=self.separate_units)
                footnote_complete, _, _ = le.find_layout(5, 2, ['$', '%'])

                threshold += 5

            if not footnote_complete:
                return None
        elif self.find_method == 'model-based':
            # get table bbox if none is provided or a it does not include a correct footnote
            if table == None:
                page = copy.copy(self.pages[0])

                tables = self.extractModelTables(image)

                if table_index >= len(tables):
                    return None
                table = tables[table_index]
            
            table_clip = page.crop(table['bbox'])

            le = LayoutExtractor(table, table_clip, separate_units=self.separate_units)
            footnote_complete, _, _ = le.find_layout(5, 2, ['$', '%'])

        table_settings = le.find_cells()
        plumber_table = table_clip.find_table(table_settings)
        if plumber_table == None:
            return None
        table['settings'] = table_settings
        table['cells'] = plumber_table.cells
        table['text'] = plumber_table.extract(x_tolerance=2)

        modified_list_of_lists = [
            [s.replace('\n', ' ') for s in inner_list if s != None]
            for inner_list in table['text']
        ]

        table['text'] = modified_list_of_lists

        if img_path != None:
            im = table_clip.to_image(resolution=300)
            im.draw_lines(table['lines'], stroke_width=3, stroke=(0,0,0)) # redraw existing lines
            im.debug_tablefinder(table_settings)
            im.save(img_path)

        return table

    def extractModelTables(self, image):
        """
        Extracts tables from the given image, by using a machine learning model.

        Parameters:
            image (Image): The image object from which the tables are to be extracted.

        Returns:
            list: A list of dictionaries representing the extracted tables. Each dictionary contains the following keys:
                - 'bbox': A list of four values representing the bounding box coordinates of the table.
                - 'lines': An empty list to store the lines of the table.
                - 'settings': An empty dictionary to store the settings of the table.
                - 'cells': An empty list to store the cells of the table.
                - 'footer': The y-coordinate of the table's footer.
                - 'header': The y-coordinate of the table's header.
        """
        table_boxes = model.predict(image.original)[0].boxes

        tables = []
        for t_i, table in enumerate(table_boxes):
            tables.append({'bbox': [x/image.scale for x in table.xyxy.tolist()[0]], 'lines': [], 'settings': {}, 'cells': []})
            tables[t_i]['footer'] = tables[t_i]['bbox'][3]
            tables[t_i]['header'] = tables[t_i]['bbox'][1]

        return tables

    def extractTablesPage(self, page_index, img_path=None):
        """
        Extracts tables from a specific page in the document.

        Parameters:
            page_index (int): The index of the page from which to extract the tables.
            img_path (str, optional): The path to save the image of the page with extracted tables.

        Returns:
            list: A list of extracted tables.
        """
        extracted_tables = []

        page = copy.copy(self.pages[page_index])
        tf = TableFinder(page)

        if img_path != None or self.find_method == 'model-based':
            image = page.to_image(resolution=300)

        if self.find_method == 'rule-based': tables_found = tf.find_tables()
        else: tables_found = self.extractModelTables(image)

        for table_index, tablebox in enumerate(tables_found):
            table = self.extractTable(page, table_index=table_index, table=tablebox)
            if table != None: 
                extracted_tables.append(table)
                if img_path != None:
                    image.draw_lines(table['lines'], stroke_width=3, stroke=(0,0,0)) # redraw existing lines
                    image.debug_tablefinder(table['settings'])
        
        if img_path != None: image.save(f'{img_path}_{page_index}.png')
        
        return extracted_tables

    def extractTables(self, page_index=None, img_path=None):
        """
        Extracts tables from the specified page or all pages if no page index is provided.
        
        Parameters:
            page_index (int): The index of the page to extract tables from. If not provided, tables will be extracted from all pages.
            img_path (str): The path to the image file containing the page. Required if page_index is provided.
        
        Returns:
            list: A list of extracted tables.
        """
        if page_index != None:
            return self.extractTablesPage(page_index, img_path)

        extracted_tables = []
        for i in range(len(self.pages)):
            extracted_tables.extend(self.extractTablesPage(i, img_path))
        
        return extracted_tables


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
    # load model
    model = YOLO('keremberke/yolov8s-table-extraction')

    # set model parameters
    model.overrides['conf'] = 0.25  # NMS confidence threshold
    model.overrides['iou'] = 0.45  # NMS IoU threshold
    model.overrides['agnostic_nms'] = False  # NMS class-agnostic
    model.overrides['max_det'] = 1000  # maximum number of detections per image

    te = TableExtractor(path="examples/pdf/FDX/2017/page_29.pdf", separate_units=False, find_method='model-based')
    tables = te.extractTables(page_index=0, img_path='table')
    
    dataframes = [te.tableToDataframe(table['text']) for table in tables]
    for i, df in enumerate(dataframes): te.export('excel', f'excel/test_{i}', dataframe=df)