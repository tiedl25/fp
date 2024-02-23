#!/usr/bin/env python3
import pdfplumber
import numpy as np
import re
import torch

if __name__ == "__main__":
    from table_finder import TableFinder
else:
    try:
        from .table_finder import TableFinder
    except ImportError:
        from table_finder import TableFinder


class LayoutExtractor:
    def __init__(self, table, clipping, separate_units=False) -> None:
        self.table = table
        self.clipping = clipping
        self.page_height = clipping.parent_page.height
        self.table_lines = sorted(self.table['lines'], key=lambda e: e['top'])
        self.separate_units = separate_units

    def extend_top_of_column(self, x, top, bottom):
        """
        Check if the top of the column can be extended. There shouldn't be any characters or ruling lines above the column separator.

        Parameters:
        - self: the object itself
        - x: x coordinate of the column separator
        - top: top of the row
        - bottom: bottom of the row

        Returns:
        - The new top of the row
        """
        # return if this is the top row of the table
        if top == self.clipping.bbox[1]:
            return top

        # get the bounding box of the separator with the given x coordinate, that lies above the row
        bbox_above_row = self.clipping.bbox.copy()
        bbox_above_row[0] = x-1
        bbox_above_row[2] = x+1
        bbox_above_row[3] = top
        intersecting_chars = self.clipping.crop(bbox_above_row).chars

        # get all ruling lines that are above the headerline and the bottom of the row
        t_lines = [t_line for t_line in self.table_lines if t_line['top'] < self.table['header']-2 and 
            t_line['top'] <= top and
            t_line['width'] < self.clipping.width * 0.9 and 
            t_line['x0'] <= x <= t_line['x1']]

        # return the bottom of the lowest intersecting character or ruling line
        if len(t_lines) > 0 and len(intersecting_chars) > 0:
            return t_lines[-1]['bottom'] if t_lines[-1]['bottom'] > intersecting_chars[-1]['bottom'] else intersecting_chars[-1]['bottom']
        elif len(intersecting_chars) > 0:
            return intersecting_chars[-1]['bottom']
        elif len(t_lines) > 0:
            return t_lines[-1]['bottom']
        
        # return the top of the table if nothing is intersecting
        return self.clipping.bbox[1]

    def find_columns(self, clipping, max_diff, special_symbols=[' ', '.', '%', '$', 'cid:127', '•', '\n', '\t'], font_diff=True):
        '''
            Define new column separator if the vertical distance between two characters is greater than max_diff or if the font changes.
            The headerline has often also another font, that creates problems with multiple column dividers where they not belong. 
            The font change is therefore only considered a column divider, if the distance to the next character is greater than 1.
            For special characters it also creates separate columns, defined by a rectangle.
        '''
        chars = [char for char in sorted(clipping.chars, key=lambda e: e['x0']) if char['text']  not in special_symbols]
        separator = []

        for i in range(len(chars)-1):
            char = chars[i+1]
            diff = char['x0'] - chars[i]['x1']

            if diff > max_diff or (font_diff and diff > 3 and char['fontname'] != chars[i]['fontname']):
                
                separator_x = char['x0']-(diff/2)

                bottom = clipping.bbox[3]

                # test table lines if they are above the headerline
                top = self.extend_top_of_column(separator_x, clipping.bbox[1], clipping.bbox[3])

                separator.append({'x0': separator_x, 'top': top, 'x1': separator_x, 'bottom': bottom, 'object_type': 'line', 'height': bottom-top})

            # special characters can be defined such as $ or % that are treated as separate columns
            #if self.separate_units and (chars[0]['text'] in special_symbols or char['text'] in special_symbols):
            #    rect = self.find_unit_column(char)
            #    self.separate_unit_column(rect)
            #    separator.append(rect)

        return separator

    def find_rows(self, clipping, max_diff):
        '''
            Define new row separator if the horizontal distance between two characters is greater than max_diff. 
            Also detect, if a footnote exists and thus separate it from the rest of the table.
        '''
        chars = [char for char in sorted(clipping.chars, key=lambda e: e['top']) if char['text'] not in [' ', '\n', '\t']]
        separator = []
        header_separator = None
        i=0
        while i < len(chars)-1:
            diff = chars[i+1]['top'] - chars[i]['bottom']
            avg = (chars[i]['bottom'] + chars[i+1]['top']) / 2

            if diff > max_diff:
                left = self.table['bbox'][0]
                right = self.table['bbox'][2]
                line = {'x0': left, 'top': avg, 'x1': right, 'bottom': avg, 'object_type': 'line', 'width': right-left}
                separator.append(line)

                # separate header if font changes for the first time
                if chars[i+1]['fontname'] != chars[i]['fontname'] and header_separator is None:
                    header_separator = avg

            i += 1

        
        table_percentage = clipping.height/self.page_height
        if header_separator is None or header_separator - clipping.bbox[1] > clipping.height * (1-table_percentage)*0.9 > 1:
            header_separator = sorted([x for x in self.table_lines if "dot_line" not in x.keys() 
                                                                and x['top'] - clipping.bbox[1] > clipping.height * 0.01 
                                                                and x['bottom'] - clipping.bbox[1] < clipping.height * (1-table_percentage) * 0.9 
                                                                and x['width'] > clipping.width * 0.3], 
                                                                key=lambda e: e['width'], reverse=True)
            if len(header_separator) == 0 or header_separator[0]['width'] < clipping.width * 0.3:
                header_separator = clipping.bbox[1]
            else:
                header_separator = max([x for x in header_separator if x['width'] == header_separator[0]['width']], key=lambda e: len(e['segments']))['top']#header_separator['top']

        return separator, header_separator
    
    def find_unit_column(self, char):
        '''
            Unit columns get a top and bottom defined by the existing lines in the table.
        '''
        self.table_lines.append({'top': self.table['footer'], 'bottom': self.table['footer']}) # footer divider should be the last line

        top, bottom = self.table['bbox'][1], self.table['footer']
        rect = {'x0': char['x0'], 'top': top, 'x1': char['x1'], 'bottom': bottom, 'y0': bottom, 'y1': top, 'doctop': bottom, 'object_type': 'rect', 'height': bottom-top, 'width': char['x1'] - char['x0'], 'symbol': char['text']}
        for i in range(len(self.table_lines)-1):
            if char['top'] >= self.table_lines[i]['bottom'] and char['bottom'] <= self.table_lines[i+1]['top']:
                rect['top'] = rect['y1'] = self.table_lines[i]['bottom']
                rect['bottom'] = rect['y0'] = rect['doctop'] = self.table_lines[i+1]['top']
                rect['height'] = rect['bottom'] - rect['top']
                break

        return rect

    def separate_unit_column(self, rect):
        '''
            Break rows in two parts if they intersect with the rectangle created from a special symbol and thus transform the column into a single cell.
        '''
        rows = []
        for row in self.row_separator:
            if rect['top'] < row['top'] and rect['bottom'] > row['bottom'] and rect['x0'] > row['x0'] and rect['x1'] < row['x1']:
                row_right = dict(row)
                row_right['x0'] = rect['x1']
                row_right['width'] = row_right['x1'] - row_right['x0']

                row['x1'] = rect['x0']
                row['width'] = row['x1'] - row['x0']

                rows.extend([row, row_right])
            else:
                rows.append(row)

        rows.append(rect) # to get the bottom and top separator
        self.row_separator = rows   

    def find_footnote(self, x_space):
        """
        Remove rows at the bottom of the table based on different criteria and find footnotes.

        Parameters:
            - self: the object itself
            - x_space (int): The max spacing between chars until a new column is created.

        Returns:
            None
        """
        separator = [x for x in self.row_separator if x['top'] > self.table['bbox'][1] and x['bottom'] < self.table['bbox'][3]]
        separator.append({'top': self.table['bbox'][3], 'bottom': self.table['bbox'][3]})

        i=len(separator)-1
        while i > 0:
            bbox = self.clipping.bbox.copy()
            bbox[1] = separator[i-1]['bottom']
            bbox[3] = separator[i]['top']
            if bbox[3] - bbox[1] <= 0:
                i-=1
                continue
            
            clip = self.clipping.crop(bbox)
            cols = self.find_columns(clip, 2*x_space, special_symbols=[' ', 'cid:127', '•'], font_diff=False)
            words = clip.extract_words()
            #width = max([w['x1'] for w in words], default=self.clipping.bbox[2]) - min([w['x0'] for w in words], default=self.clipping.bbox[0])
            leading_space = words[0]['x0'] - bbox[0] if len(words) > 0 else self.clipping.width
            trailing_space = bbox[2] - words[-1]['x1'] if len(words) > 0 else self.clipping.width

            # remove single lines within first 10% of table width
            if len(cols) == 0 and leading_space < self.clipping.width * 0.1:
                self.table['bbox'][3] = bbox[1]
                if self.table['footer'] > bbox[1]: self.table['footer'] = bbox[1]
            # remove centered lines
            elif len(cols) == 0 and np.isclose(leading_space, trailing_space, 0.2) and leading_space != self.clipping.width:
                self.table['bbox'][3] = bbox[1]
                if self.table['footer'] > bbox[1]: self.table['footer'] = bbox[1] 
            # remove footnotes -> # or (#) or #. or #) or *
            else:
                if len(cols) == 1 and leading_space < self.clipping.width * 0.1 and re.search("^\(\d+\)$|^\*$|^\d+\.$|^\d+\)$|^\d+$|^•$|^cid:127$|^\([a-z]\)$", words[0]['text']) is not None:
                    self.table['footer'] = bbox[1]
                else:
                    break

            i-=1
        
        return

    def remove_at_top(self, x_space):
        """
        Removes rows at the top of the table based on different criteria.

        Parameters:
        - self: the object itself
        - x_space: The max spacing between chars until a new column is created.

        Returns:
        - None
        """
        separator = self.row_separator.copy()
        separator.insert(0, {'top': self.table['bbox'][1], 'bottom': self.table['bbox'][1]})

        i=0
        while i < len(separator)-1:
            bbox = self.clipping.bbox.copy()
            bbox[1] = separator[i]['bottom']
            bbox[3] = separator[i+1]['top']
            if bbox[3] - bbox[1] <= 0:
                i+=1
                continue
            
            clip = self.clipping.crop(bbox)
            cols = self.find_columns(clip, 3*x_space, special_symbols=[' ', 'cid:127', '•'], font_diff=False)
            words = clip.extract_words()
            #width = max([w['x1'] for w in words], default=self.clipping.bbox[2]) - min([w['x0'] for w in words], default=self.clipping.bbox[0])
            leading_space = words[0]['x0'] - bbox[0] if len(words) > 0 else self.clipping.width
            trailing_space = bbox[2] - words[-1]['x1'] if len(words) > 0 else self.clipping.width

            # remove single lines within first 10% of table width
            if len(cols) == 0 and leading_space < self.clipping.width * 0.05:
                self.table['bbox'][1] = bbox[3]
                if self.table['header'] < bbox[3]: self.table['header'] = bbox[3]
            # remove centered lines
            elif len(cols) == 0 and np.isclose(leading_space, trailing_space, 0.2) and leading_space != self.clipping.width:
                self.table['bbox'][1] = bbox[3]
                if self.table['header'] < bbox[3]: self.table['header'] = bbox[3]
            # remove footnotes -> # or (#) or #. or #) or *
            else:
                if len(cols) == 1 and leading_space < self.clipping.width * 0.05 and re.search("^\(\d+\)$|^\*$|^\d+\.$|^\d+\)$|^\d+$", words[0]['text']) is not None:
                    self.table['bbox'][1] = bbox[3]
                    if self.table['header'] < bbox[3]: self.table['header'] = bbox[3]
                else:
                    break

            i+=1
        
        return        

    def remove_unessessary_columns(self):
        self.column_separator = sorted(self.column_separator, key=lambda e: e['x0'])
        i=0
        while i < len(self.column_separator)-1:
            l1 = self.column_separator[i]
            l2 = self.column_separator[i+1]

            if l1['x0'] == l2['x0']:
                i+=1
                continue
            min_bottom = min(l1['bottom'], l2['bottom'])
            max_top = max(l1['top'], l2['top'])
            if max_top >= min_bottom-2:
                i+=1
                continue
            bbox = [l1['x0'], max_top+1, l2['x1']-1, min_bottom]
            try: 
                if len([x for x in self.clipping.crop(bbox).chars if x['text'] !=' ']) != 0:
                    i+=1
                    continue
            except:
                i+=1
                continue
            
            if l1['top'] < l2['top'] and l1['bottom'] < l2['bottom']:
                l2['top'] = l1['bottom']
            elif l1['top'] > l2['top'] and l1['bottom'] > l2['bottom']:
                l1['top'] = l2['bottom']
            elif l1['height'] < l2['height']:
                self.column_separator.pop(i)
                #i+=1
            elif l1['height'] > l2['height']:
                self.column_separator.pop(i+1)
            i+=1

    def find_layout(self, x_space, y_space=-0.3, symbols=[' ', '.', '%', 'cid:127', '•']):
        """
        Find the layout of the table based on the provided x and y spaces and symbols.

        Parameters:
            x_space (int): The max spacing between chars until a new column is created.
            y_space (int): The max spacing between lines until a new row is created.
            symbols (list): List of special symbols that should be ignored. (deprecated)

        Returns:
            tuple: A tuple containing the column separators and row separators.
        """

        self.column_separator = []

        # find rows and header
        self.row_separator, self.table['header'] = self.find_rows(self.clipping, y_space)
        self.remove_at_top(x_space=x_space)
        self.find_footnote(x_space=x_space)
        # adjust left and right border after removing rows at top
        self.clipping = self.clipping.crop(self.table['bbox'])
        try: 
            self.table['bbox'][0] = min([x['x0'] for x in self.clipping.chars if x['text'] != ' '])
            self.table['bbox'][1] = min([x['top'] for x in self.clipping.chars if x['text'] != ' '])
            self.table['bbox'][2] = max([x['x1'] for x in self.clipping.chars if x['text'] != ' '])
            self.table['bbox'][3] = max([x['bottom'] for x in self.clipping.chars if x['text'] != ' '])
            if self.table['bbox'][3] < self.table['footer']: self.table['footer'] = self.table['bbox'][3]
            self.clipping.crop(self.table['bbox'])
        except:
            return [], []        
        self.row_separator, self.table['header'] = self.find_rows(self.clipping, y_space)

        # add the ruling lines to the list of rows
        self.row_separator.extend([{'x0': self.table['bbox'][0], 'x1': self.table['bbox'][2], 'width': self.table['bbox'][2] - self.table['bbox'][0], 'object_type': 'line', 'top': x['top'], 'bottom': x['bottom']} for x in self.table['lines']])
        self.row_separator.sort(key=lambda e: e['top'])

        # table is separated in horizontal segments for individual column detection for header and body -> this is important for multi-header tables
        # segments are defined by the top and bottom lines of the table, the header and the footer and the ruling lines that are above the headerline
        segments = [{'top': self.table['bbox'][1]}]
        if self.table['header'] != self.table['bbox'][1]: 
            segments.extend([x for x in self.table_lines if x['top'] < self.table['header']])
            segments.append({'top': self.table['header'], 'bottom': self.table['header']})
        segments.append({'top': self.table['footer'], 'bottom': self.table['footer']})
        if self.table['footer'] != self.table['bbox'][3]: segments.append({'top': self.table['bbox'][3], 'bottom': self.table['bbox'][3]})

        i=0
        # find columns in each segment
        while i < len(segments)-1:
            bbox = self.clipping.bbox.copy()
            bbox[1] = segments[i]['top']
            bbox[3] = segments[i+1]['bottom']
            try: 
                cols = self.find_columns(self.clipping.crop(bbox), x_space, symbols)
            except Exception as e: 
                i+=1
                continue

            self.column_separator.extend(cols)

            i+=1

        self.remove_unessessary_columns()

        return self.column_separator, self.row_separator

    def find_model_layout(self, structure_model, structure_image_processor):
        table = self.table['bbox'].copy()
        table[0]-=20 if table[0]-20 > self.clipping.parent_page.bbox[0] else self.clipping.parent_page.bbox[0]
        table[2]+=20 if table[2]+20 < self.clipping.parent_page.bbox[2] else self.clipping.parent_page.bbox[2]
        table[1]-=20 if table[1]-20 > self.clipping.parent_page.bbox[1] else self.clipping.parent_page.bbox[1]
        table[3]+=20 if table[3]+20 < self.clipping.parent_page.bbox[3] else self.clipping.parent_page.bbox[3]
        image = self.clipping.parent_page.crop(table).to_image(resolution=300)
        
        inputs = structure_image_processor(images=image.original, return_tensors="pt")
        outputs = structure_model(**inputs)

        # convert outputs (bounding boxes and class logits) to Pascal VOC format (xmin, ymin, xmax, ymax)
        target_sizes = torch.tensor([(image.original.size[::-1][0]/image.scale, image.original.size[::-1][1]/image.scale)])
        results = structure_image_processor.post_process_object_detection(outputs, threshold=0.7, target_sizes=target_sizes)[0]

        boxes = []
        derived_tables = []
        for score, label, box in zip(results["scores"], results["labels"], results["boxes"]):
            bbox = [a+b for a, b in zip([table[0], table[1], table[0], table[1]], box.tolist())] # reorder and scale
            #bbox = self.extend_table(top_threshold=2, bottom_threshold=2, bbox=bbox)
            boxes.append({'label': structure_model.config.id2label[label.item()], 'score': score.item(), 'bbox': bbox})
        
        self.column_separator = [{'x0': x['bbox'][0], 'x1': x['bbox'][0], 'width': 0, 'height': x['bbox'][3] - x['bbox'][1], 'object_type': 'line', 'top': x['bbox'][1], 'bottom': x['bbox'][3]} for x in boxes if x['label'] in ['table column', 'table column header']] + \
                                [{'x0': x['bbox'][2], 'x1': x['bbox'][2], 'width': 0, 'height': x['bbox'][3] - x['bbox'][1], 'object_type': 'line', 'top': x['bbox'][1], 'bottom': x['bbox'][3]} for x in boxes if x['label'] in ['table column', 'table column header']]
        self.row_separator = [{'x0': x['bbox'][0], 'x1': x['bbox'][2], 'width': x['bbox'][2] - x['bbox'][0], 'height': 0, 'object_type': 'line', 'top': x['bbox'][1], 'bottom': x['bbox'][1]} for x in boxes if x['label'] in ['table row', 'table spanning cell']] + \
                             [{'x0': x['bbox'][0], 'x1': x['bbox'][2], 'width': x['bbox'][2] - x['bbox'][0], 'height': 0, 'object_type': 'line', 'top': x['bbox'][3], 'bottom': x['bbox'][3]} for x in boxes if x['label'] in ['table row', 'table spanning cell']]
        return self.column_separator, self.row_separator

    def get_table_settings(self):
        vertical_lines = [self.table['bbox'][0], self.table['bbox'][2]] # left and right line
        horizontal_lines = [self.table['bbox'][1], self.table['footer']] # top and bottom line
        #horizontal_lines.extend(self.table['lines'])
        if "column_separator" in vars(self).keys():
            vertical_lines.extend(self.column_separator)
        if "row_separator" in vars(self).keys():
            horizontal_lines.extend([x for x in self.row_separator if x['top'] < self.table['footer']])

        table_settings = {
            "vertical_strategy": "explicit",
            "horizontal_strategy": "explicit",
            "snap_tolerance": 3,
            "text_tolerance": 0,
            "intersection_y_tolerance": 5,
            "join_tolerance": 0,
            "min_words_vertical": 0,
            "min_words_horizontal": 0,
            "explicit_vertical_lines": vertical_lines,
            "explicit_horizontal_lines": horizontal_lines
        }

        return table_settings

if __name__ == '__main__':
    path = "examples/pdf/FDX/2017/page_27.pdf"

    with pdfplumber.open(path) as pdf:
        page = pdf.pages[0]
        t_finder = TableFinder(page)
        tables = t_finder.find_tables()
        table_clip = page.crop(tables[0]['bbox'])

    le = LayoutExtractor(tables[0], table_clip)
    footnote_complete, column_separator, row_separator = le.find_layout(5, 2, ['$', '%'])
        
    im = table_clip.to_image(resolution=300)

    table_settings = le.get_table_settings()

    im.debug_tablefinder(table_settings)
    
    im.save('table.png')