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
        chars = sorted(self.page.crop(bbox).chars, key=lambda e: e['top'])
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
                    return chars[i]['top'] - 1   
                i+=1

        return chars[len(chars)-1]['top'] - 1

    def find_table_bottom(self, bbox, max_diff):
        chars = sorted(self.page.crop(bbox).chars, key=lambda e: e['bottom'])
        chars.insert(0, {'top': bbox[1], 'bottom': bbox[1], 'text': '_'})

        i=0
        while i < len(chars)-1:
            # remove white spaces
            if chars[i+1]['text'] == ' ':
                chars.pop(i+1)
            else:
                diff = chars[i+1]['top'] - chars[i]['bottom']
                if diff > max_diff:
                    return chars[i]['bottom'] + 1
                i+=1


        return chars[len(chars)-1]['bottom'] +1
    
    def find_table_left(self, bbox, max_diff):
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
                    return chars[i]['x0'] -1
                i+=1


        return chars[len(chars)-1]['x0'] -1
    
    def find_table_right(self, bbox, max_diff):
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
                    return chars[i]['x1'] + 1
                i+=1


        return chars[len(chars)-1]['x1'] +1

    def concat_lines(self, lst):
        '''
            Concatenate line elements with the same distance to the top of the page, that are not recognized as one
        '''
        concat_lines = []
        current_line = lst.pop(0)

        for i, line in enumerate(lst):
            if current_line['top'] == line['top']:
                if line['x1'] > current_line['x1']:
                    current_line['x1'] = line['x1']
                    current_line['width'] = current_line['width'] + line['width']
                    current_line['pts'][1] = line['pts'][1]
            else:
                concat_lines.append(current_line)
                current_line = line

        concat_lines.append(current_line) #append last line also to concat_lines

        return concat_lines

    def derive_tables(self):
        '''
            Look for overlapping tables and merge them together
        '''
        table = self.tables.pop(0)
        derived_tables = [table]

        for i, bbox in enumerate(self.tables):
            #table side | bbox side
            ll = bbox[0] < table[0] #bbox left side is on the left of the table
            lr = bbox[2] < table[0] #bbox right side is on the left of the table
            rr = bbox[2] > table[2] #bbox right side is on the right of the table
            rl = bbox[0] > table[2] #bbox left side is on the right of the table
            tt = bbox[1] < table[1] #bbox top side is on top of the table
            tb = bbox[3] < table[1] #bbox bottom side is on top of the table
            bb = bbox[3] > table[3] #bbox bottom side is below the table
            bt = bbox[1] > table[3] #bbox top side is below the table

            l_inside = not (ll and rl)
            r_inside = not (lr and rr)
            b_inside = not (tb and bb)
            t_inside = not (tt and bt)

            #     2
            # 1 _____ 3
            #   |   |
            # 8 |   | 4
            #   |   |
            # 7 ----- 5
            #     6
            # --> numbers refer to intersecting tables
            
            if ll and rr and tt and bb: # table is inside bbox
                table = bbox
            elif (ll and lr) or (rr and rl) or (tt and tb) or (bb and bt): # bbox is next to the table -> completely unrelated
                derived_tables.append(bbox)
            elif l_inside and rr:
                table[2] = bbox[2] # 3 4 5
                if b_inside and tt:
                    table[1] = bbox[1] # 3
                elif t_inside and bb:
                    table[3] = bbox[3] # 5
            elif r_inside and ll:
                table[0] = bbox[0] # 7 8 1
                if b_inside and tt:
                    table[1] = bbox[1] # 7
                elif t_inside and bb:
                    table[3] = bbox[3] # 1
            elif b_inside and tt:
                table[1] = bbox[1] # 1 2 3 --> in reality only 2
            elif t_inside and bb:
                table[3] = bbox[3] # 5 6 7 --> in reality only 6 

        return derived_tables

    def find_tables(self):
        '''
            Find tables in a given pdf page
        '''
        self.lines.sort(key = lambda e: e['top'])
        self.lines = self.concat_lines(self.page.lines)

        #return self.lines
        for i, line in enumerate(self.lines):
            #if line['non_stroking_color'] != None and len(line['non_stroking_color']) > 2:
            #    if line['stroking_color'] != line['non_stroking_color']:
            #        continue
            
            bottom = self.find_table_bottom([line['x0'], line['top'], line['x1'], self.page.height], 5)
            top = self.find_table_top([line['x0'], 0, line['x1'], line['bottom']], 4)
            left = self.find_table_left([0, top, line['x0'], bottom], 2)
            right = self.find_table_right([line['x1'], top, self.page.width, bottom], 2)

            bbox = [left, top, right, bottom]
            
            self.tables.append(bbox)

        #return self.tables
        derived_tables = []
        if (len(self.tables)>0):
            while True:
                self.tables = self.derive_tables()

                derived_tables.append(self.tables.pop(0))
                if len(self.tables) == 0:
                    break
                if len(self.tables) == 1:
                    derived_tables.append(self.tables.pop(0))
                    break

            self.tables = derived_tables

        return derived_tables
    
if __name__ == '__main__':
    tables = []

    with pdfplumber.open("examples/pdf/FDX/2017/page_31.pdf") as pdf:
        page = pdf.pages[0]
        t_finder = TableFinder(page)
        tables = t_finder.find_tables()

        im = page.to_image(resolution=300)
        im.draw_rects(tables)
        im.save("test.png")
