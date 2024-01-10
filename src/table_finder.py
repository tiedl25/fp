import pdfplumber
import statistics

class TableFinder:
    def __init__(self, page) -> None:
        self.page = page
        self.lines = page.lines
        self.tables = []

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
        chars = sorted(self.page.crop(bbox, strict=False).chars, key=lambda e: e['top'])
        chars.reverse()
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

        return chars[len(chars)-1]['top'] if len(chars) > 0 else bbox[3]

    def find_table_bottom(self, bbox, max_diff):
        """
        Find the bottom boundary of a table in the given bounding box.

        Parameters:
            bbox (tuple): The bounding box of the table.
            max_diff (int): The maximum difference allowed between the top of one character and the bottom of the previous character.

        Returns:
            int: The bottom coordinate of the table.

        """
        chars = sorted(self.page.crop(bbox, strict=False).chars, key=lambda e: e['bottom'])
        chars.insert(0, {'top': bbox[1], 'bottom': bbox[1], 'text': '_'})

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


        return chars[len(chars)-1]['bottom']
    
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

        chars = sorted(self.page.crop(bbox).chars, key=lambda e: e['x1'])
        chars.reverse()
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


        return chars[len(chars)-1]['x0']
    
    def find_table_right(self, bbox, max_diff):
        """
        Finds the right boundary of a table within the given bounding box.

        Parameters:
            bbox (list): The bounding box coordinates of the table.
            max_diff (int): The maximum allowed difference between adjacent characters.

        Returns:
            int: The x-coordinate of the rightmost position of the table.
        """
        if bbox[2] == bbox[0]:
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


        return chars[len(chars)-1]['x1']

    def concat_lines(self, lst):
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

        for i, line in enumerate(lst):
            if current_line['top'] == line['top']:
                if line['x1'] > current_line['x1']:
                    current_line['x1'] = line['x1']
                    current_line['width'] = current_line['width'] + line['width']
                    current_line['pts'][1] = line['pts'][1]
            else:
                if current_line['x0'] < self.page.bbox[0] or current_line['top'] < self.page.bbox[1]:
                    continue
                concat_lines.append(current_line)
                current_line = line

        if current_line['x0'] < self.page.bbox[0] or current_line['top'] < self.page.bbox[1]:
            return concat_lines

        concat_lines.append(current_line) #append last line also to concat_lines

        return concat_lines
    
    def collapse_rects(self):
        """
        Collapse the rectangles in the page.

        This function iterates through the list of rectangles in the page and collapses any rectangles 
        with a height less than 1 and a fill value of True. The collapsed rectangles are then appended 
        to the list of lines.

        Returns:
            A list of dictionaries representing the collapsed lines.

        """
        lines = []

        for i, rect in enumerate(self.page.rects):
            if rect['height'] < 1 and rect['fill'] == True:
                rect['object_type'] = "line"
                lines.append(rect)

        return lines

    def derive_tables(self):
        """
        Look for overlapping tables and merge them together

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

            #table side | bbox side
            ll = bbox[0] < table_bbox[0] #bbox left side is on the left of the table
            lr = bbox[2] < table_bbox[0] #bbox right side is on the left of the table
            rr = bbox[2] > table_bbox[2] #bbox right side is on the right of the table
            rl = bbox[0] > table_bbox[2] #bbox left side is on the right of the table
            tt = bbox[1] < table_bbox[1] #bbox top side is on top of the table
            tb = bbox[3] < table_bbox[1] #bbox bottom side is on top of the table
            bb = bbox[3] > table_bbox[3] #bbox bottom side is below the table
            bt = bbox[1] > table_bbox[3] #bbox top side is below the table

            l_inside = not (ll or rl)
            r_inside = not (lr or rr)
            b_inside = not (tb or bb)
            t_inside = not (tt or bt)

            #     2
            # 1 _____ 3
            #   |   |
            # 8 |   | 4
            #   |   |
            # 7 ----- 5
            #     6
            # --> numbers refer to intersecting tables
            
            if ll and rr and tt and bb: # table is inside bbox
                table_bbox = bbox
                table['lines'].insert(0, test_table['lines'][0])
            elif (ll and lr) or (rr and rl) or (tt and tb) or (bb and bt): # bbox is next to the table -> completely unrelated
                derived_tables.append(test_table)
            elif l_inside and r_inside and t_inside and b_inside:
                table['lines'].append(test_table['lines'][0])
            else:
                if l_inside and rr:
                    table['lines'].append(test_table['lines'][0])
                    table_bbox[2] = bbox[2] # 3 4 5
                    if b_inside and tt:
                        table_bbox[1] = bbox[1] # 3
                    elif t_inside and bb:
                        table_bbox[3] = bbox[3] # 5
                elif r_inside and ll:
                    table['lines'].append(test_table['lines'][0])
                    table_bbox[0] = bbox[0] # 7 8 1
                    if b_inside and tt:
                        table_bbox[1] = bbox[1] # 7
                    elif t_inside and bb:
                        table_bbox[3] = bbox[3] # 1
                elif b_inside and tt:
                    table['lines'].append(test_table['lines'][0])
                    table_bbox[1] = bbox[1] # 1 2 3 --> in reality only 2
                elif t_inside and bb:
                    table['lines'].append(test_table['lines'][0])
                    table_bbox[3] = bbox[3] # 5 6 7 --> in reality only 6 
                elif l_inside and r_inside:
                    table['lines'].append(test_table['lines'][0])

                    if tt:
                        table_bbox[1] = bbox[1]
                    if bb:
                        table_bbox[3] = bbox[3]
                elif b_inside and t_inside:
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

    def determine_average_line_height(self):
        chars = sorted(self.page.chars, key=lambda e: e['bottom'])

        diff = []
        for i in range(len(chars)-1):
            if chars[i]['text'] == ' ':
                continue
            d = chars[i+1]['bottom'] - chars[i]['top']
            if d > 0:
                diff.append(d)

        return statistics.mode(diff)
        
    def find_tables(self, bottom_threshold=5, top_threshold=4, left_threshold=2, right_threshold=2):
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

        bottom_threshold = self.determine_average_line_height()

        self.lines = [x for x in self.lines if x['x0'] != x['x1']] # remove vertical lines
        self.lines.extend(self.collapse_rects())
        self.lines.sort(key = lambda e: e['top'])
        self.lines = self.concat_lines(self.lines)
        for i, line in enumerate(self.lines):
            if line['x0'] >= line['x1']:
                continue
            
            bottom = self.find_table_bottom([line['x0'], line['top'], line['x1'], self.page.bbox[3]], bottom_threshold)
            top = self.find_table_top([line['x0'], self.page.bbox[1], line['x1'], line['bottom']], top_threshold)

            if top >= bottom:
                continue
                
            left = self.find_table_left([self.page.bbox[0], top, line['x0'], bottom], left_threshold)
            right = self.find_table_right([line['x1'], top, self.page.bbox[2], bottom], right_threshold)

            mid = self.page.width/2
            objs = self.page.crop([mid-5, top, mid+5, bottom])
            objs = objs.chars + objs.lines
            if len(objs) > 0:#not ((mid-5 < left and mid-5 < right) or (mid+5 > left and mid+5 > right)):
                left = self.page.bbox[0]#self.find_table_left([self.page.bbox[0], top, left, bottom], 50)

            bbox = [left, top, right, bottom]

            bbox = self.extend_table(bbox)

            if len(objs) > 0: bbox[0] = self.find_table_left(bbox, 200)

            table = {'bbox': bbox, 'lines': [line]}

            self.tables.append(table)

        #return self.tables
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
        
        return derived_tables
    
if __name__ == '__main__':
    tables = []

    with pdfplumber.open("fintabnet/pdf/AAL/2003/page_64.pdf") as pdf:
        page = pdf.pages[0]
        t_finder = TableFinder(page)
        tables = t_finder.find_tables()

        im = page.to_image(resolution=300)
        bboxes = [x['bbox'] for x in tables]
        im.draw_rects(bboxes)
        im.save("test.png")
