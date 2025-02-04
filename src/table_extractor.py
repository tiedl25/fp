#!/usr/bin/env python3
import pandas as pd
import pdfplumber
import copy
import statistics
import os
import regex as re
import numpy as np
import json

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
    def __init__(self, path, separate_units=False, detection_method='rule-based', layout_method='rule-based', model=None, image_processor=None, layout_model=None, layout_processor=None, max_column_space=4, max_row_space=-0.3):
        self.path = path
        pdf = pdfplumber.open(path)
        self.pages = pdf.pages
        self.separate_units = separate_units
        self.detection_method = detection_method
        self.layout_method = layout_method
        self.model = model
        self.image_processor = image_processor
        self.layout_model = layout_model
        self.layout_processor = layout_processor
        self.max_column_space = max_column_space
        self.max_row_space = max_row_space

    def tableToDataframe(self, table):
        """
        Converts a table into a pandas DataFrame. Header cells with None type are merged with the next column.

        Parameters:
            table (list): The table to be converted.

        Returns:
            pandas.DataFrame: The converted table as a DataFrame.
        """

        header = table['header']
        layout = table['layout'].copy()
        t = []
        for row in layout:
            if row[0]['bbox'][3] <= header:
                if len(t) == 0:
                    t.append([x['text'] for x in row])
                else:
                    for i, cell in enumerate(row):
                        t[0][i] += ' ' + cell['text']
            else:
                t.append([x['text'] for x in row])

        if table['header'] == table['bbox'][1]:
            pd.DataFrame(t)
        return pd.DataFrame(t[1:], columns=t[0])
    
    def export(self, format, path, dataframe=None, table=None, overwrite=False):
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

        if format not in ['excel', 'csv', 'json']:
            return None

        if os.path.exists(f"{path}.{format if format != 'excel' else 'xlsx'}") and overwrite==False:
            inp = input("File already exists. Overwrite (yes/no)?\n")
            if inp not in ["y", "yes"]: return

        if format == "json":
            return json.dump(table, open(f'{path}.json', 'w'))

        if dataframe is None:
            if table is None:
                return
            try: dataframe = self.tableToDataframe(table)
            except: print(f'Error when exporting table in {path}'); return

        if format == 'excel':
            return dataframe.to_excel(f'{path}.xlsx', index=False)    
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
        cell[0]+=0.2
        cell[1]+=0.5
        cell[2]-=0.2
        cell[3]-=0.5
        pagecrop = [x for x in page.crop(cell).chars if x['text'] not in [' ', '.']] # remove white spaces and dots because they should not be part of the cell

        b1 = min(pagecrop, key=lambda e: e['x0'], default={'x0': cell[0]-0.2})
        b2 = min(pagecrop, key=lambda e: e['top'], default={'top': cell[1]-0.5})
        b3 = max(pagecrop, key=lambda e: e['x1'], default={'x1': cell[2]+0.2})
        b4 = max(pagecrop, key=lambda e: e['bottom'], default={'bottom': cell[3]+0.5})

        return [b1['x0'], b2['top'], b3['x1'], b4['bottom']]

    def merge_cells(self, pdfplumber_table, table, page):
        """
        Merge cells in the PDF table based on certain conditions.

        Parameters:
            pdfplumber_table: the pdfplumber table object
            table: the table dictionary
            page: the pdfplumber page object
        """
        dot_lines = [x for x in table['lines'] if 'dot_line' in x.keys()]

        i=0
        while i < len(pdfplumber_table.rows):
            row = pdfplumber_table.rows[i]

            idxs = [i for i,x in enumerate(pdfplumber_table.extract()[i]) if x != '' and x is not None]

            if len(idxs) == 0:
                i+=1
                continue

            cell = row.cells[idxs[0]]

            # merge rows in the header that share the same layout and are not intersecting with a ruling line
            if cell[3] <= table['header'] and i < len(pdfplumber_table.rows)-1:
                cells = [x for x in row.cells if x is not None]
                next_cells = [x for x in pdfplumber_table.rows[i+1].cells if x is not None]
                if len(cells) != len(next_cells):
                    i+=1
                    continue
                bbox = table['bbox'].copy()
                bbox[3] = next_cells[0][3]-2
                bbox[1] = cells[0][1]
                lines = page.crop(bbox).lines
                if len(lines) > 0 or bbox[3] > table['header']:
                    i+=1
                    continue

                cell_top = cell[1]
                for cell in pdfplumber_table.rows[i].cells:
                    if cell != None: pdfplumber_table.cells.remove(cell)

                for next_cell in pdfplumber_table.rows[i].cells:
                    if next_cell is None:
                        continue
                    lst = list(next_cell)
                    lst[1] = cell_top
                    new_cell = tuple(lst)
                    pdfplumber_table.cells.append(new_cell)
                    pdfplumber_table.cells.remove(next_cell)
                
                continue         

            try: chars = [x for x in page.crop(cell).chars if x['text'] != ' ']
            except: continue

            if len(chars) == 0:
                i+=1
                continue
            

            # merge cells in the first column in the body
            if len(idxs) == 1 and idxs[0] == 0 and i < len(pdfplumber_table.rows)-1:
                if chars[-1]['text'] == ':':
                    i+=1
                    continue
                
                # text in line is centered -> title
                if chars[0]['x0'] - table['bbox'][0] > 10 and np.isclose(chars[0]['x0']-cell[0], cell[2]-chars[-1]['x1'], 0.3):
                    i+=1
                    continue
                
                # check if the cell is not intersecting with a dot sequence
                intersecting_dot_lines = [dot_line for dot_line in dot_lines if cell[0] < dot_line['x0'] < cell[2] and cell[1] <= dot_line['top'] < dot_line['bottom'] <= cell[3]]
                if len(intersecting_dot_lines) > 0:
                    i+=1
                    continue
                

                next_cell = pdfplumber_table.rows[i+1].cells[idxs[0]]
                if next_cell is None:
                    i+=1
                    continue

                next_row_char = [x for x in page.crop(next_cell).chars if x['text'] != ' ']
                if len(next_row_char) == 0:
                    i+=1
                    continue
                
                # continue if the text does not contain a letter
                if re.search("[a-z, A-Z]", ''.join([x['text'] for x in next_row_char])) is None:
                    i+=1
                    continue

                # continue if the font changes between the two rows
                if chars[0]['fontname'] != next_row_char[0]['fontname'] or min([x['top'] for x in next_row_char]) - max([x['bottom'] for x in chars]) > self.max_column_space * 1.5:
                    i+=1
                    continue

                bbox = table['bbox'].copy()
                bbox[3] = next_cell[3]
                bbox[1] = cell[1]+1
                lines = page.crop(bbox).lines
                if len(lines) > 0:
                    #if len(tuple([x['top'] for x in lines])) == 1:
                    i+=1
                    continue

                # merge both cells
                cell_top = cell[1]
                for cell in pdfplumber_table.rows[i].cells:
                    if cell != None: pdfplumber_table.cells.remove(cell)
                for next_cell in pdfplumber_table.rows[i].cells:
                    if next_cell is None:
                        continue
                    lst = list(next_cell)
                    lst[1] = cell_top
                    new_cell = tuple(lst)
                    pdfplumber_table.cells.append(new_cell)
                    pdfplumber_table.cells.remove(next_cell)

            # merge cells in the second column in the body
            elif len(idxs) == 1 and idxs[0] > 0 and i!= 0:
                previous_cell = pdfplumber_table.rows[i-1].cells[idxs[0]]
                if previous_cell is None:
                    i+=1
                    continue

                previous_row_char = [x for x in page.crop(previous_cell).chars if x['text'] != ' ']
                if len(previous_row_char) == 0:
                    i+=1
                    continue            

                if re.search("[a-z, A-Z]", ''.join([x['text'] for x in previous_row_char])) is None:
                    i+=1
                    continue

                if chars[0]['fontname'] != previous_row_char[0]['fontname'] or min([x['top'] for x in chars]) - max([x['bottom'] for x in previous_row_char]) > self.max_column_space * 1.5:
                    i+=1
                    continue
                
                bbox = table['bbox'].copy()
                bbox[1] = previous_cell[1]
                bbox[3] = cell[3]-1
                if len(page.crop(bbox).lines) > 0:
                    i+=1
                    continue

                # merge both cells
                cell_bottom = cell[3]
                for previous_cell in pdfplumber_table.rows[i-1].cells:
                    if previous_cell is None:
                        continue
                    lst = list(previous_cell)
                    lst[3] = cell_bottom
                    new_cell = tuple(lst)
                    pdfplumber_table.cells.append(new_cell)
                    pdfplumber_table.cells.remove(previous_cell)
                for cell in pdfplumber_table.rows[i].cells:
                    if cell != None: pdfplumber_table.cells.remove(cell)
            else:
                i+=1

    def extractTable(self, page, table_index=0, table=None, img_path=None, image=None, overwrite=False):
        """
        Extracts a table from a given page. Either by rule-based or custom method, based on pdfplumbers table extraction.

        Args:
            page (Page): The page object from which to extract the table.
            table_index (int): The index of the table to extract. Default is 0.
            table (dict): The table dictionary containing the table's bounding box and other information. If not provided, the function will find the bbox of the table. Only important with direct calling of the function. 
            img_path (str): The path where the extracted table image should be saved. Default is None.
            image (PIL.Image.Image): The image of the page. If not provided, the function will use the image from the page object.
            overwrite (bool): Whether to overwrite the image if it already exists. Default is False.

        Returns:
            dict: The table dictionary containing the table's bounding box, settings, cells, and extracted text. Returns None if no table is found.
        """
        # get table bbox if none is provided
        if table == None:
            page = copy.copy(self.pages[0])
            tf = TableFinder(page, model=self.model, image_processor=self.image_processor)
            tables = tf.find_tables(detection_method=self.detection_method, image=image if image is not None else page.to_image(resolution=300))

            if table_index >= len(tables):
                return None
            table = tables[table_index]
        
        try: page_crop = page.crop(table['bbox'])
        except: return None

        # get table with the table settings
        le = LayoutExtractor(table, page_crop, separate_units=self.separate_units)
        if self.layout_model is None and self.layout_processor is None: 
            col_sep, row_sep = le.find_layout(self.max_column_space, self.max_row_space)
        else:
            col_sep, row_sep = le.find_model_layout(self.layout_model, self.layout_processor)
        table['settings'] = le.get_table_settings()
        pdfplumber_table = page_crop.find_table(table['settings'])

        if pdfplumber_table == None or len(pdfplumber_table.rows) <= 2 or len(col_sep) == 0:
            return None

        # merge cells only with the rule-based layout detection
        if self.layout_method != 'model-based': self.merge_cells(pdfplumber_table, table, page)
       
        # reformat and shrink table cells and define layout
        table_cells = []
        table_layout = []
        for row in pdfplumber_table.rows:
            row_layout = []
            last_cell_text = ''
            for cell in row.cells:
                try: 
                    if cell is None:
                        row_layout.append({'bbox': None, 'text': last_cell_text})
                        continue

                    bbox = self.shrink_cell(page, list(cell))
                    if bbox == list(cell) or bbox[0] == bbox[2] or bbox[1] == bbox[3]: 
                        text = ''
                    else:
                        text = page_crop.crop(bbox).extract_text()                 
                        table_cells.append({'bbox': bbox, 'text': text.replace('\n', ' ').replace('.', ''), 'original_bbox': cell})
                        text = text.replace('\n', ' ').replace(' . ', '').replace('..', '')
                    row_layout.append({'bbox': bbox, 'text': text})
                    last_cell_text = text
                except:
                    continue

            table_layout.append(row_layout)

        table['cells'] = table_cells
        table['layout'] = table_layout
        
        # save image
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

        tf = None
        le = None

        return table

    def extractTablesInPage(self, page_index, img_path=None, overwrite=False):
        """
        Extracts tables from a specific page in the document.

        Parameters:
            page_index (int): The index of the page from which to extract the tables.
            img_path (str): The path to save the image of the page with extracted tables.
            overwrite (bool): Whether to overwrite the image if it already exists.

        Returns:
            list: A list of extracted tables.
        """
        extracted_tables = []

        page = self.pages.copy()[page_index]
        tf = TableFinder(page, model=self.model, image_processor=self.image_processor)

        image=None
        if img_path is not None or self.detection_method == 'model-based' or self.layout_method == 'model-based':
            image = page.to_image(resolution=300)

        tables_found = tf.find_tables(detection_method=self.detection_method, image=image)

        # get table layout and cells for every table
        for table_index, tablebox in enumerate(tables_found):
            table = self.extractTable(page, table_index=table_index, table=tablebox, image=image)
            if table is None: 
                continue

            extracted_tables.append(table)
            if img_path is None:
                continue

            image.draw_rect(table['bbox'])
            image.draw_rects(x['bbox'] for x in table['cells'])
            image.draw_hline(table['footer'])
            image.draw_hline(table['header'])
        
        # save image
        if img_path is not None: 
            if not os.path.exists(img_path): os.mkdir(img_path)
            name = f'{img_path}/{self.path.replace("/", "_")[0:-4]}_page_{page_index}.png'
            if os.path.exists(name) and overwrite==False:
                inp = input("File already exists. Overwrite (yes/no)?\n")
                if inp in ["y", "yes"]: image.save(name)
            else: image.save(name)


        tf = None
        
       
        tf = None
        
        return extracted_tables

    def extractTables(self, page_index=None, img_path=None, overwrite=False):
        """
        Extracts tables from the specified page or all pages if no page index is provided.
        
        Parameters:
            page_index (int): The index of the page to extract tables from. If not provided, tables will be extracted from all pages.
            img_path (str): The path to the image file containing the page. Required if page_index is provided.
            overwrite (bool): Whether to overwrite the image if it already exists.
        
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
    detection_method = 'rule-based'
    layout_method = 'rule-based'

    model = None
    image_processor = None
    structure_model = None
    structure_image_processor = None

    if detection_method == 'model-based':
        image_processor = AutoImageProcessor.from_pretrained("microsoft/table-transformer-detection")
        model = TableTransformerForObjectDetection.from_pretrained("microsoft/table-transformer-detection")
    if layout_method == 'model-based':
        structure_image_processor = AutoImageProcessor.from_pretrained("microsoft/table-transformer-structure-recognition")
        structure_model = TableTransformerForObjectDetection.from_pretrained("microsoft/table-transformer-structure-recognition")       
    
    te = TableExtractor(path="examples/pdf/FDX/2017/page_26.pdf", separate_units=False, detection_method=detection_method, layout_method=layout_method, model=model, image_processor=image_processor, layout_model=structure_model, layout_processor=structure_image_processor, max_column_space=4, max_row_space=-0.3)
    tables = te.extractTables(img_path='.', overwrite=True)
    
    dataframes = [te.tableToDataframe(table) for table in tables]
    if not os.path.exists("excel"): os.mkdir("excel")
    for i, df in enumerate(dataframes): te.export('excel', f'excel/test_{i}', dataframe=df)