import pandas as pd
import pdfplumber
import copy
import statistics
import os

from ultralyticsplus import YOLO, render_result

from transformers import AutoImageProcessor, TableTransformerForObjectDetection

if __name__ == '__main__':  
    from table_finder import TableFinder
    from layout_extractor import LayoutExtractor
else:
    try: from .table_finder import TableFinder
    except: from table_finder import TableFinder
    try: from .layout_extractor import LayoutExtractor
    except: from layout_extractor import LayoutExtractor

class TableExtractor:
    def __init__(self, path, separate_units=False, find_method='rule-based', model=None, image_processor=None, determine_row_space="min", max_column_space=5, max_row_space=2):
        self.path = path
        pdf = pdfplumber.open(path)
        self.pages = pdf.pages
        self.separate_units = separate_units
        self.find_method = find_method
        self.model = model
        self.image_processor = image_processor
        self.max_columns_space = max_column_space
        self.max_row_space = max_row_space
        self.determine_row_space = determine_row_space

    def tableToDataframe(self, table):
        """
        Converts a table into a pandas DataFrame. Header cells with None type are merged with the next column.

        Parameters:
            table (list): The table to be converted.

        Returns:
            pandas.DataFrame: The converted table as a DataFrame.
        """
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
        """
        Export data to a file in the specified format.

        Args:
            format (str): The format of the file to export (either 'excel' or 'csv').
            path (str): The path to save the exported file.
            dataframe (pandas.DataFrame, optional): The DataFrame to export. If not provided,
                the data will be extracted from the table parameter.
            table (str, optional): The name of the table to export. If dataframe is not provided,
                the data will be extracted from this table.

        Returns:
            None: If dataframe and table are both None.
            None: If an invalid format is provided.
            None: If an error occurs during the export process.
        """
        if dataframe is None:
            if table is None:
                return
            dataframe = self.tableToDataframe(table)

        if format == 'excel':
            return dataframe.to_excel(f'{path}.xlsx')    
        elif format == 'csv':
            return dataframe.to_latex(f'{path}.csv', index=False)      

    def shrink_cell(self, page, cell):
        """
        Calculate the coordinates of the smallest bounding box that contains all non-empty characters within a given cell on a page.

        Parameters:
            page (Page): The page object containing the cell.
            cell (tuple): The coordinates of the cell in the format (x0, y0, x1, y1).

        Returns:
            list: The coordinates of the smallest bounding box in the format [x0, y0, x1, y1].
        """
        pagecrop = [x for x in page.crop(cell).chars if x['text'] not in [' ', '.']] # remove white spaces and dots because they should not be part of the cell

        b1 = min(pagecrop, key=lambda e: e['x0'], default={'x0': cell[0]})
        b2 = min(pagecrop, key=lambda e: e['top'], default={'top': cell[1]})
        b3 = max(pagecrop, key=lambda e: e['x1'], default={'x1': cell[2]})
        b4 = max(pagecrop, key=lambda e: e['bottom'], default={'bottom': cell[3]})

        return [b1['x0'], b2['top'], b3['x1'], b4['bottom']]

    def determine_max_linepitch(self, page):
        if self.determine_row_space == "value": return self.max_row_space

        chars = sorted(page.chars, key=lambda e: e['top'])
        chars = [char for char in chars if char['text'] != ' ']

        diff = []
        for i in range(len(chars)-1):
            d = chars[i+1]['top'] - chars[i]['bottom']
            if d > 0:
                diff.append(d)

        return min(diff)-0.1 if self.determine_row_space == "min" else statistics.mode(diff)-0.1

    def extractTable(self, page, table_index=0, table=None, img_path=None, image=None, overwrite=False):
        """
        Extracts a table from a given page. Either by rule-based or custom method based on pdfplumbers table extraction.
        For the later method, the bounding box is retrieved with the TableFinder class and the columns and rows with the LayoutExtractor class.
        Those columns/rows can be specified as explicit lines in the table_settings and are then used to extract the cells.

        Args:
            page (Page): The page object from which to extract the table.
            table_index (int): The index of the table to extract. Default is 0.
            table (dict): The table dictionary containing the table's bounding box and other information. If not provided, the function will find the bbox of the table. Only important with direct calling of the function. 
            img_path (str): The path where the extracted table image should be saved. Default is None.
            image (PIL.Image.Image): The image of the page. If not provided, the function will use the image from the page object.

        Returns:
            dict: The table dictionary containing the table's bounding box, settings, cells, and extracted text. Returns None if no table is found.
        """
        # rule-based
        if self.find_method == 'rule-based':
            footnote_complete = False
            threshold = 5 # max_diff for finding table bottom
            
            # increase threshold if the footnote is incomplete and try again to find the table
            while not footnote_complete and threshold < 20: 
                
                # get table bbox if none is provided or the footnote is incomplete
                if table == None or threshold > 5:
                    page = copy.copy(self.pages[0])
                    tf = TableFinder(page)
                    tables = tf.find_tables(bottom_threshold=threshold)

                    if table_index >= len(tables):
                        return None
                    table = tables[table_index]

                page_crop = page.crop(table['bbox'])
                le = LayoutExtractor(table, page_crop, separate_units=self.separate_units)
                footnote_complete, _, _ = le.find_layout(self.max_columns_space, self.determine_max_linepitch(page), ['$', '%'])

                threshold += 5

            if not footnote_complete:
                return None

        # model-based
        elif self.find_method in ['model-based', 'microsoft']:
            # get table bbox if none is provided
            if table == None:
                page = copy.copy(self.pages[0])

                tf = TableFinder(page, model=self.model, image_processor=self.image_processor)
                tables = tf.find_tables(find_method=self.find_method, image=image if image is not None else page.to_image(resolution=300))

                if table_index >= len(tables):
                    return None
                table = tables[table_index]
            
            page_crop = page.crop(table['bbox'])

            le = LayoutExtractor(table, page_crop, separate_units=self.separate_units)
            # TODO average line height
            le.find_layout(self.max_columns_space, self.determine_max_linepitch(page), ['$', '%'], ignore_footnote=True)


        # for both methods

        table['settings'] = le.get_table_settings()
        pdfplumber_table = page_crop.find_table(table['settings'])

        if pdfplumber_table == None:
            return None

        table_cells = []
        for cell in pdfplumber_table.cells: 
            bbox = self.shrink_cell(page, cell)
            try: 
                text = page_crop.crop(bbox).extract_text().replace('\n', ' ')
                if text == '':
                    continue
                table_cells.append({'bbox': bbox, 'text': text})
            except: continue

        # reformatted cells
        table['cells'] = table_cells

        # original cells
        table['pdfplumber_cells'] = {'cells': pdfplumber_table.cells, 'text': pdfplumber_table.extract(x_tolerance=2)}

        if img_path is not None: 
            image = page_crop.to_image(resolution=300)
            image.draw_lines(table['lines'], stroke_width=3, stroke=(0,0,0)) # redraw existing lines
            image.debug_tablefinder(table['settings'])
            if not os.path.exists(img_path): os.mkdir(img_path)
            name = f'{img_path}/{os.path.basename(self.path)[0:-4]}_table_{table_index}.png'
            if os.path.exists(name) and overwrite==False:
                inp = input("File already exists. Overwrite (yes/no)?\n")
                if inp in ["y", "yes"]: image.save(name)
            else: image.save(name)

        return table

    def extractTablesInPage(self, page_index, img_path=None, overwrite=False):
        """
        Extracts tables from a specific page in the document.

        Parameters:
            page_index (int): The index of the page from which to extract the tables.
            img_path (str, optional): The path to save the image of the page with extracted tables.

        Returns:
            list: A list of extracted tables.
        """
        extracted_tables = []

        page = self.pages.copy()[page_index]
        tf = TableFinder(page, model=self.model, image_processor=self.image_processor)

        image=None
        if img_path is not None or self.find_method in ['model-based', 'microsoft']:
            image = page.to_image(resolution=300)

        tables_found = tf.find_tables(find_method=self.find_method, image=image)

        for table_index, tablebox in enumerate(tables_found):
            table = self.extractTable(page, table_index=table_index, table=tablebox, image=image)
            if table is None: 
                continue

            extracted_tables.append(table)
            if img_path is None:
                continue

            #image.draw_hlines([x['top'] for x in table['lines']], stroke_width=3, stroke=(230, 65, 67, 65)) # redraw existing lines
            #image.debug_tablefinder(table['settings'])
            image.draw_rect(table['bbox'])
            #image.draw_rects(x['bbox'] for x in table['cells'])
            image.draw_hline(table['footer'])
            image.draw_hline(table['header'])
            #image.draw_vline(page.width/2)
        
        if img_path is not None: 
            if not os.path.exists(img_path): os.mkdir(img_path)
            name = f'{img_path}/{os.path.basename(self.path)[0:-4]}_page_{page_index}.png'
            if os.path.exists(name) and overwrite==False:
                inp = input("File already exists. Overwrite (yes/no)?\n")
                if inp in ["y", "yes"]: image.save(name)
            else: image.save(name)
        
        return extracted_tables

    def extractTables(self, page_index=None, img_path=None, overwrite=False):
        """
        Extracts tables from the specified page or all pages if no page index is provided.
        
        Parameters:
            page_index (int): The index of the page to extract tables from. If not provided, tables will be extracted from all pages.
            img_path (str): The path to the image file containing the page. Required if page_index is provided.
        
        Returns:
            list: A list of extracted tables.
        """
        if page_index != None:
            return self.extractTablesInPage(page_index, img_path, overwrite)

        extracted_tables = []
        for i in range(len(self.pages)):
            extracted_tables.extend(self.extractTablesInPage(i, img_path, overwrite))
        
        return extracted_tables

if __name__ == '__main__':  
    find_method = 'rule-based'

    if find_method == 'model-based':
        # load model
        model = YOLO('keremberke/yolov8s-table-extraction')

        # set model parameters
        model.overrides['conf'] = 0.25  # NMS confidence threshold
        model.overrides['iou'] = 0.45  # NMS IoU threshold
        model.overrides['agnostic_nms'] = False  # NMS class-agnostic
        model.overrides['max_det'] = 10  # maximum number of detections per image

        image_processor = None
    elif find_method == 'microsoft':
        image_processor = AutoImageProcessor.from_pretrained("microsoft/table-transformer-detection")
        model = TableTransformerForObjectDetection.from_pretrained("microsoft/table-transformer-detection")
    else :
        model = None    
        image_processor = None

    te = TableExtractor(path="fintabnet/pdf/A/2007/page_71.pdf", separate_units=False, find_method=find_method, model=model, image_processor=image_processor, determine_row_space="min", max_column_space=4, max_row_space=2)
    tables = te.extractTables(img_path='.')
    
    #dataframes = [te.tableToDataframe(table['pdfplumber_cells']['text']) for table in tables]
    #for i, df in enumerate(dataframes): te.export('excel', f'excel/test_{i}', dataframe=df)