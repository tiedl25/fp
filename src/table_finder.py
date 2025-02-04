#!/usr/bin/env python3
import pdfplumber
import statistics
import itertools
import torch

class TableFinder:
    def __init__(self, page, model=None, image_processor=None) -> None:
        self.page = page
        self.lines = page.lines
        self.tables = []
        self.model = model
        self.image_processor = image_processor

    def find_table_top(self, bbox, max_diff, must_contain_chars=False):
        """
        Find the top boundary of the table within a given bounding box. 

        Args:
            bbox (tuple): The bounding box coordinates (left, top, right, bottom).
            max_diff (int): The maximum allowed difference in top position between characters.
            must_contain_chars (bool, optional): Whether the table must contain characters. Defaults to True.

        Returns:
            int: The top position of the table.

        """
        chars = sorted(self.page.crop(bbox, strict=False).chars, key=lambda e: e['top'], reverse=True)
        if not must_contain_chars: chars.insert(0, {'top': bbox[3], 'bottom': bbox[3], 'text': '_'})

        i=0
        while i < len(chars)-1:
            # remove white spaces
            if chars[i+1]['text'] == ' ':
                chars.pop(i+1)
            else:
                diff = chars[i]['top'] - chars[i+1]['bottom']
                if diff > max_diff:
                    return chars[i]['top']
                i+=1

        return chars[-1]['top'] if len(chars) > 0 else bbox[3]

    def find_table_bottom(self, bbox, max_diff, must_contain_chars=False):
        """
        Find the bottom boundary of a table in the given bounding box.

        Parameters:
            bbox (tuple): The bounding box of the table.
            max_diff (int): The maximum difference allowed between the top of one character and the bottom of the previous character.

        Returns:
            int: The bottom coordinate of the table.

        """
        chars = sorted(self.page.crop(bbox, strict=False).chars, key=lambda e: e['bottom'])
        if not must_contain_chars: chars.insert(0, {'top': bbox[1], 'bottom': bbox[1], 'text': '_'})

        i=0
        while i < len(chars)-1:
            # remove white spaces
            if chars[i+1]['text'] == ' ':
                chars.pop(i+1)
            else:
                diff = chars[i+1]['top'] - chars[i]['bottom']
                if diff > max_diff:
                    return chars[i]['bottom']
                i+=1


        return chars[-1]['bottom'] if len(chars) > 0 else bbox[1]
   
    def find_table_left(self, bbox, max_diff):
        """
        Find the left boundary of a table within the given bounding box.

        Parameters:
            bbox (list): The bounding box coordinates of the table as a list of four integers [x0, y0, x1, y1].
            max_diff (int): The maximum difference in x-coordinate allowed between adjacent characters.

        Returns:
            int: The leftmost x-coordinate of the table.
        """
        if bbox[0] == bbox[2]:
            return self.page.bbox[0]

        chars = sorted(self.page.crop(bbox).chars, key=lambda e: e['x1'], reverse=True)
        chars.insert(0, {'x0': bbox[2], 'x1': bbox[2], 'text': '_'})

        i=0
        while i < len(chars)-1:
            # remove white spaces
            if chars[i+1]['text'] == ' ':
                chars.pop(i+1)
            else:
                diff = chars[i]['x0'] - chars[i+1]['x1']
                if diff > max_diff:
                    return chars[i]['x0']
                i+=1


        return chars[-1]['x0']
    
    def find_table_right(self, bbox, max_diff):
        """
        Finds the right boundary of a table within the given bounding box.

        Parameters:
            bbox (list): The bounding box coordinates of the table.
            max_diff (int): The maximum allowed difference between adjacent characters.

        Returns:
            int: The x-coordinate of the rightmost position of the table.
        """
        if bbox[2] <= bbox[0]:
            return self.page.bbox[2]

        chars = sorted(self.page.crop(bbox).chars, key=lambda e: e['x0'])
        chars.insert(0, {'x0': bbox[0], 'x1': bbox[0], 'text': '_'})

        i=0
        while i < len(chars)-1:
            # remove white spaces
            if chars[i+1]['text'] == ' ':
                chars.pop(i+1)
            else:
                diff = chars[i+1]['x0'] - chars[i]['x1']
                if diff > max_diff:
                    return chars[i]['x1']
                i+=1


        return chars[-1]['x1']

    def concat_lines(self, lst):
        """
        Concatenate lines with the same distance to the top of the page.

        Args:
            lst (list): A list of dictionaries representing lines.

        Returns:
            list: A list of dictionaries representing concatenated lines.
        """
        concat_line_segments = []
        if len(lst) == 0:
            return concat_line_segments
        current_line = lst.pop(0)

        for i, line in enumerate(lst):
            if current_line['top'] == line['top'] and line['x1'] > current_line['x1'] and line['x0'] <= current_line['x1']:
                current_line['x1'] = line['x1']
                current_line['width'] = current_line['width'] + line['width']
                current_line['pts'][1] = line['pts'][1]

            else:
                if current_line['x0'] < self.page.bbox[0] or current_line['top'] < self.page.bbox[1]:
                    current_line = line
                    continue
                concat_line_segments.append(current_line)
                current_line = line

        if current_line['x0'] < self.page.bbox[0] or current_line['top'] < self.page.bbox[1]:
            return concat_line_segments

        concat_line_segments.append(current_line) #append last line also to concat_lines

        return concat_line_segments
    
    def concat_line_segments(self, lst):
        """
        Concatenate line elements with the same distance to the top of the page, that are not recognized as one

        Args:
            lst (list): A list of dictionaries representing lines.

        Returns:
            list: A list of dictionaries representing concatenated lines.
        """
        concat_lines = []
        if len(lst) == 0:
            return concat_lines
        current_line = lst.pop(0)
        current_line['segments'] = [current_line.copy()]

        for line in lst:
            if current_line['top'] == line['top'] and line['x1'] > current_line['x1']:
                current_line['x1'] = line['x1']
                current_line['pts'][1] = line['pts'][1]
                current_line['segments'].append(line)
            else:
                current_line['width'] = current_line['segments'][-1]['x1'] - current_line['segments'][0]['x0'] if len(current_line['segments']) > 0 else current_line['segments'][0]['width']
                concat_lines.append(current_line)
                current_line = line
                current_line['segments'] = [current_line.copy()]
                
        #append last line also to concat_lines
        concat_lines.append(current_line) 

        return concat_lines
    
    def collapse_rects_and_curves(self):
        """
        Collapse the rectangles in the page.

        This function iterates through the list of rectangles in the page and collapses any rectangles 
        with a height less than 1 and a fill value of True. The collapsed rectangles are then appended 
        to the list of lines.

        Returns:
            A list of dictionaries representing the collapsed lines.

        """
        lines = []

        for i, rect in enumerate(self.page.rects+self.page.curves):
            if rect['height'] < 5 and rect['fill'] == True:
                rect['object_type'] = "line"
                lines.append(rect)

        return lines

    def find_lines_of_dots(self):
        """
        Finds and groups the lines of dots in the given page based on their y-coordinates and proximity in x-coordinates.
        Returns a list of dictionaries representing the lines of dots, each containing the x-coordinate range, top and bottom y-coordinates, width, height, and a flag indicating if it's a dot line.
        """
        dots = [x for x in self.page.chars if x['text'] == '.']

        dots_grouped_by_y = [list(group) for key, group in itertools.groupby(sorted(dots, key=lambda e: e['top']), lambda e: e['top'])]
        lines = []
        current_group = None
        for dot_group in dots_grouped_by_y:
            for dot in dot_group:
                if current_group == None:
                    current_group = [dot]
                elif current_group[-1]['x1'] < dot['x0'] < current_group[-1]['x1'] + 7:
                    current_group.append(dot)
                else:
                    if len(current_group) > 3:
                        x0 = min(current_group, key=lambda e: e['x0'])['x0']
                        x1 = max(current_group, key=lambda e: e['x1'])['x1']
                        lines.append({'x0': x0, 'x1': x1, 'top': current_group[0]['bottom'], 'bottom': current_group[0]['bottom'], 'width': x1 - x0, 'height': 1, 'dot_line': True})
                    current_group = [dot]

        return lines

    def derive_tables(self, bottom_threshold=10, top_threshold=10, left_threshold=5, right_threshold=5):
        """
        Look for overlapping tables and merge them into a single table.

        Parameters:
            self (object): The object instance.
        
        Returns:
            dict: The derived table.
        """
        table = self.tables.pop(0)
        derived_tables = []
    
        for i, test_table in enumerate(self.tables):
            bbox = test_table['bbox']
            table_bbox = table['bbox']

            ll = bbox[0] + left_threshold < table_bbox[0] #bbox left side is on the left of the table
            lr = bbox[2] + left_threshold < table_bbox[0] #bbox right side is on the left of the table
            rr = bbox[2] - right_threshold > table_bbox[2] #bbox right side is on the right of the table
            rl = bbox[0] - right_threshold > table_bbox[2] #bbox left side is on the right of the table
            tt = bbox[1] + top_threshold < table_bbox[1] #bbox top side is on top of the table
            tb = bbox[3] + top_threshold < table_bbox[1] #bbox bottom side is on top of the table
            bb = bbox[3] - bottom_threshold > table_bbox[3] #bbox bottom side is below the table
            bt = bbox[1] - bottom_threshold > table_bbox[3] #bbox top side is below the table

            l_inside = not (ll or rl)
            r_inside = not (lr or rr)
            b_inside = not (tb or bb)
            t_inside = not (tt or bt)
            
            if ll and rr and tt and bb: # table is inside bbox
                table_bbox = bbox
                table['lines'].insert(0, test_table['lines'][0])
            elif (ll and lr) or (rr and rl) or (tt and tb) or (bb and bt): # bbox is next to the table
                derived_tables.append(test_table)
            elif l_inside and r_inside and t_inside and b_inside: # bbox is inside of the table
                table['lines'].append(test_table['lines'][0])
            else:
                if l_inside and rr: # bbox right side is on the right of the table -> extend right
                    if len(test_table['lines']) > 0: 
                        table['lines'].append(test_table['lines'][0])
                    table_bbox[2] = bbox[2] 
                    if b_inside and tt: # bbox top side is on top of the table -> extend top
                        table_bbox[1] = bbox[1] 
                    elif t_inside and bb: # bbox bottom side is below the table -> extend bottom
                        table_bbox[3] = bbox[3] 
                elif r_inside and ll: # bbox left side is on the left of the table -> extend left
                    if len(test_table['lines']) > 0: 
                        table['lines'].append(test_table['lines'][0])
                    table_bbox[0] = bbox[0] 
                    if b_inside and tt: # bbox top side is on top of the table -> extend top
                        table_bbox[1] = bbox[1] 
                    elif t_inside and bb: # bbox bottom side is below the table -> extend bottom
                        table_bbox[3] = bbox[3] 
                elif b_inside and tt: # bbox top side is on top of the table -> extend top
                    if len(test_table['lines']) > 0: 
                        table['lines'].append(test_table['lines'][0])
                    table_bbox[1] = bbox[1] 
                elif t_inside and bb: # bbox bottom side is below the table -> extend bottom
                    if len(test_table['lines']) > 0: 
                        table['lines'].append(test_table['lines'][0])
                    table_bbox[3] = bbox[3] 
                elif l_inside and r_inside: # bbox is between left and right of the table
                    if len(test_table['lines']) > 0: 
                        table['lines'].append(test_table['lines'][0])
                    if tt:
                        table_bbox[1] = bbox[1]
                    if bb:
                        table_bbox[3] = bbox[3]
                elif b_inside and t_inside: # bbox is between top and bottom of the table
                    if len(test_table['lines']) > 0: 
                        table['lines'].append(test_table['lines'][0])
                    if rr:
                        table_bbox[2] = bbox[2]
                    if ll: 
                        table_bbox[0] = bbox[0]

                if tt and bb:
                    table_bbox[1] = bbox[1]
                    table_bbox[3] = bbox[3]

                if rr and ll:
                    table_bbox[0] = bbox[0]
                    table_bbox[2] = bbox[2]

        self.tables = derived_tables
        return table

    def extend_table(self, bbox, bottom_threshold=5, top_threshold=4, left_threshold=5, right_threshold=2):
        """
        Extends the table bounding box in all four directions (bottom, top, left, right) based on the given thresholds.

        Parameters:
            bbox (list): The current bounding box of the table in the format [left, top, right, bottom].
            bottom_threshold (int): The maximum number of pixels to extend the bottom of the table.
            top_threshold (int): The maximum number of pixels to extend the top of the table.
            left_threshold (int): The maximum number of pixels to extend the left of the table.
            right_threshold (int): The maximum number of pixels to extend the right of the table.

        Returns:
            list: The updated bounding box of the table in the format [left, top, right, bottom].
        """
        bbox_old = bbox
        while True:
            bottom = self.find_table_bottom([bbox[0], bbox[3], bbox[2], self.page.bbox[3]], bottom_threshold)
            top = self.find_table_top([bbox[0], self.page.bbox[1], bbox[2], bbox[1]], top_threshold, must_contain_chars=False)
            left = self.find_table_left([self.page.bbox[0], top, bbox[0], bottom], left_threshold)
            right = self.find_table_right([bbox[2], top, self.page.bbox[2], bottom], right_threshold)

            bbox = [left, top, right, bottom]

            if bbox_old == bbox:
                break
            bbox_old = bbox

        return bbox

    def line_threshold(self):
        """
        Calculate the mode of the vertical distances between characters in the page. 
        """
        chars = sorted(self.page.chars, key=lambda e: e['bottom'])

        diff = []
        for i in range(len(chars)-1):
            if chars[i]['text'] == ' ':
                continue
            d = chars[i+1]['bottom'] - chars[i]['top']
            if d > 0:
                diff.append(d)

        return statistics.mode(diff)
        
    def one_column_layout(self, top, bottom, mid):
        """
        Determine if table takes whole page width or lies in one of the columns of the page.
        
        Parameters:
            top (int): The y-coordinate of the top of the cropping region.
            bottom (int): The y-coordinate of the bottom of the cropping region.
        
        Returns:
            bool: True if the table lies in one column, False otherwise.
        """
        objs = self.page.crop([mid, top if top > self.page.bbox[1] else self.page.bbox[1], mid+3, bottom if bottom < self.page.bbox[3] else self.page.bbox[3]], strict=False)
        objs = objs.chars + [x for x in objs.lines if x['fill'] == True] + objs.rects

        mid_chars = self.page.crop([mid, self.page.bbox[1], mid+3, self.page.bbox[3]], strict=False).chars
        sum_height = sum(x['height'] for x in mid_chars)

        return len(objs) > 1 or sum_height > self.page.height * 0.3
            
    def find_tables(self, bottom_threshold=5, top_threshold=4, left_threshold=2, right_threshold=2, detection_method='rule-based', image=None):
        """
        Finds tables in the given document based on certain thresholds.
        
        Args:
            bottom_threshold (int): The threshold for the bottom position of a table. Default is 5.
            top_threshold (int): The threshold for the top position of a table. Default is 4.
            left_threshold (int): The threshold for the left position of a table. Default is 2.
            right_threshold (int): The threshold for the right position of a table. Default is 2.
        
        Returns:
            list: A list of derived tables found in the document.
        """
        self.lines.extend(self.collapse_rects_and_curves())
        self.lines = [x for x in self.lines if x['x0'] != x['x1'] and x['top'] >= self.page.bbox[1] and x['bottom'] <= self.page.bbox[3] and x['x0'] >= self.page.bbox[0] and x['x1'] <= self.page.bbox[2]] # remove vertical lines
        self.lines.sort(key = lambda e: e['top'])
        line_segments = self.concat_lines(self.lines)
        self.lines = self.concat_line_segments(line_segments)

        chars = sorted([x for x in self.page.chars if x['matrix'][1] == 0 and x['matrix'][2] == 0 and x['text'] != ' ' and x['x0'] >= self.page.bbox[0] and x['x1'] <= self.page.bbox[2]], key=lambda e: e['x0'])

        # look for characters in the middle of the page -> one column page layout
        mid = (chars[0]['x0'] + chars[-1]['x1'])/2
        mid_chars = self.page.crop([mid, self.page.bbox[1], mid+3, self.page.bbox[3]], strict=False).chars
        two_column = sum(x['height'] for x in mid_chars) < self.page.height * 0.05
        if two_column:
            self.lines = [x for x in self.lines if x['width'] < (chars[-1]['x1'] - chars[0]['x0']) * 0.5]

        # extend lines with sequences of dots
        all_lines = self.find_lines_of_dots() + self.lines
        all_lines.sort(key = lambda e: e['top'])

        if detection_method == 'rule-based':
            bottom_threshold = self.line_threshold()

            # find a bbox for each line
            for i, line in enumerate(all_lines):
                if line['x0'] >= line['x1']:
                    continue
                
                bottom = self.find_table_bottom([line['x0'], line['top'], line['x1'], self.page.bbox[3]], bottom_threshold)
                top = self.find_table_top([line['x0'], self.page.bbox[1], line['x1'], line['bottom']], top_threshold, must_contain_chars=True)

                if top >= bottom:
                    continue

                if not two_column or self.one_column_layout(top-top_threshold, bottom+bottom_threshold, mid):
                    chars = sorted([x for x in self.page.chars if x['matrix'][1] == 0 and x['matrix'][2] == 0 and x['text'] != ' ' and x['x0'] >= self.page.bbox[0] and x['x1'] <= self.page.bbox[2]], key=lambda e: e['x0'])
                    left, right = chars[0]['x0'], chars[-1]['x1']
                else: 
                    left = self.find_table_left([self.page.bbox[0], top, line['x0'], bottom], left_threshold)
                    right = self.find_table_right([line['x1'], top, self.page.bbox[2], bottom], right_threshold)

                bbox = self.extend_table([left, top, right, bottom])

                table = {'bbox': bbox, 'lines': [line]}

                self.tables.append(table)

        elif detection_method == 'model-based' and self.model is not None and image is not None and self.image_processor is not None:
            inputs = self.image_processor(images=image.original, return_tensors="pt")
            outputs = self.model(**inputs)

            # convert outputs (bounding boxes and class logits) to Pascal VOC format (xmin, ymin, xmax, ymax)
            target_sizes = torch.tensor([image.original.size[::-1]])
            results = self.image_processor.post_process_object_detection(outputs, threshold=0.5, target_sizes=target_sizes)[0]

            boxes = []
            #derived_tables = []
            for score, label, box in zip(results["scores"], results["labels"], results["boxes"]):
                bbox = [round(i/image.scale, 2) for i in box.tolist()] # reorder and scale
                bbox = self.extend_table(top_threshold=2, bottom_threshold=2, bbox=bbox) # extend

                chars = self.page.crop(bbox).chars
                if len(chars) == 0:
                    continue

                bbox[0] = min(chars, key=lambda e: e['x0'])['x0']
                bbox[1] = min(chars, key=lambda e: e['top'])['top']
                bbox[2] = max(chars, key=lambda e: e['x1'])['x1']
                bbox[3] = max(chars, key=lambda e: e['bottom'])['bottom']

                table = {'bbox': bbox, 'lines': self.lines, 'settings': {}, 'cells': []}
                table['footer'] = table['bbox'][3]
                table['header'] = table['bbox'][1]
                self.tables.append(table)

            derived_tables = self.tables     
        
        # merge the bounding boxes
        derived_tables = []
        if (len(self.tables)>0):
            while True:
                new_table = self.derive_tables()
                new_table['footer'] = new_table['bbox'][3]
                new_table['header'] = new_table['bbox'][1]
                derived_tables.append(new_table)
                if len(self.tables) == 0:
                    break
                if len(self.tables) == 1:
                    new_table = self.tables.pop(0)
                    new_table['footer'] = new_table['bbox'][3]
                    new_table['header'] = new_table['bbox'][1]
                    derived_tables.append(new_table)
                    break
        
            self.tables = derived_tables
            
        # Make sure that all the lines are within the table
        for t in derived_tables:
            t['lines'] = [x for x in t['lines'] if (x['x0']>=t['bbox'][0]-5 and x['x1']<=t['bbox'][2]+5 and
                                                    x['top']>=t['bbox'][1] and x['bottom']<=t['bbox'][3])]

        return derived_tables