import pdfplumber

class TableFinder:
    def __init__(self, page) -> None:
        self.page = page
        self.lines = page.lines
        self.tables = []

    def max_diff(self, lst):
        '''
            Find a maximum difference between characters y-values, that is suitable as decision maker between 'inside-table' and 'outside-table'
        '''
        # TODO: Implement based on a average line pitch
        max_diff = float('inf')

        for i in range(len(lst)-1):
            diff = lst[i+1]['top'] - lst[i]['bottom']
            if diff != 0: 
                max_diff = min(max_diff, diff)
                return max_diff

        return max_diff

    def find_table_top(self, bbox, max_diff):
        chars = sorted(self.page.crop(bbox, strict=False).chars, key=lambda e: e['top'])
        chars.reverse()
        chars.insert(0, {'top': bbox[3], 'bottom': bbox[3], 'text': '_'})

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

        return chars[len(chars)-1]['top']

    def find_table_bottom(self, bbox, max_diff):
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
        '''
            Concatenate line elements with the same distance to the top of the page, that are not recognized as one
        '''
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
                if current_line['x0'] < 0 or current_line['y1'] < 0 or current_line['top'] < self.page.bbox[1]:
                    continue
                concat_lines.append(current_line)
                current_line = line

        if current_line['x0'] < 0 or current_line['y1'] < 0 or current_line['top'] < self.page.bbox[1]:
            return concat_lines

        concat_lines.append(current_line) #append last line also to concat_lines

        return concat_lines

    def derive_tables(self):
        '''
            Look for overlapping tables and merge them together
        '''
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

    def find_tables(self, bottom_threshold=5, top_threshold=4, left_threshold=2, right_threshold=2):
        '''
            Find tables in a given pdf page
        '''
        self.lines = [x for x in self.lines if x['x0'] != x['x1']] # remove vertical lines

        self.lines.sort(key = lambda e: e['top'])
        self.lines = self.concat_lines(self.lines)
        for i, line in enumerate(self.lines):
            #if line['non_stroking_color'] != None and len(line['non_stroking_color']) > 2:
            #    if line['stroking_color'] != line['non_stroking_color']:
            #        continue

            if line['x0'] >= line['x1']:
                continue
            
            bottom = self.find_table_bottom([line['x0'], line['top'], line['x1'], self.page.bbox[3]], bottom_threshold)
            top = self.find_table_top([line['x0'], self.page.bbox[1], line['x1'], line['bottom']], top_threshold)

            if top >= bottom:
                continue
                
            left = self.find_table_left([self.page.bbox[0], top, line['x0'], bottom], left_threshold)
            right = self.find_table_right([line['x1'], top, self.page.bbox[2], bottom], right_threshold)

            bbox = [left, top, right, bottom]
            
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

    with pdfplumber.open("examples/pdf/FDX/2017/page_80.pdf") as pdf:
        page = pdf.pages[0]
        t_finder = TableFinder(page)
        tables = t_finder.find_tables()

        im = page.to_image(resolution=300)
        bboxes = [x['bbox'] for x in tables]
        im.draw_rects(bboxes)
        im.save("test.png")
