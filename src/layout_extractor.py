import pdfplumber
import copy
import statistics

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
        self.table_lines = sorted(self.table['lines'], key=lambda e: e['top'])
        self.separate_units = separate_units

    def find_columns(self, clipping, max_diff, special_symbols):
        '''
            Define new column separator if the vertical distance between two characters is greater than max_diff or if the font changes.
            The headerline has often also another font, that creates problems with multiple column dividers where they not belong. 
            The font change is therefore only considered a column divider, if the distance to the next character is greater than 1.
            For special characters it also creates separate columns, defined by a rectangle.
        '''
        chars = sorted(clipping.chars, key=lambda e: e['x0'])
        chars = [char for char in chars if char['text']  not in [' ', '.']]
        #separator = [chars[0]['x0']-2]
        separator = []

        for i in range(len(chars)-1):
            char = chars[i+1]
            diff = char['x0'] - chars[i]['x1']

            if diff > max_diff or (diff > 3 and char['fontname'] != chars[i]['fontname']):
                top, bottom = clipping.bbox[1], clipping.bbox[3]
                x = char['x0']-(diff/2)#char['x0']-2
                separator.append({'x0': x, 'top': top, 'x1': x, 'bottom': bottom, 'object_type': 'line', 'height': bottom-top})

            # special characters can be defined such as $ or % that are treated as separate columns
            if self.separate_units and (chars[0]['text'] in special_symbols or char['text'] in special_symbols):
                rect = self.find_unit_column(char)
                self.separate_unit_column(rect)
                separator.append(rect)

        return separator

    def find_rows(self, clipping, max_diff):
        '''
            Define new row separator if the horizontal distance between two characters is greater than max_diff. 
            Also detect, if a footnote exists and thus separate it from the rest of the table.
        '''
        chars = sorted(clipping.chars, key=lambda e: e['top'])
        chars = [char for char in chars if char['text'] != ' ']
        separator = []
        footnote_complete = None
        footnote_separator = []
        header_separator = None

        for i in range(len(chars)-1):
            diff = chars[i+1]['top'] - chars[i]['bottom']
            avg = (chars[i]['bottom'] + chars[i+1]['top']) / 2

            if diff >= max_diff:
                left = self.table['bbox'][0]
                right = self.table['bbox'][2]
                line = {'x0': left, 'top': avg, 'x1': right, 'bottom': avg, 'object_type': 'line', 'width': right-left}
                footnote_separator.append(line) if footnote_complete else separator.append(line)

            # separate header if font changes for the first time
            if chars[i+1]['fontname'] != chars[i]['fontname'] and header_separator is None:
                header_separator = avg if diff > 0 else chars[i]['top']#self.table['bbox'][1]

            # separate footer
            #if chars[i+1]['size'] != chars[i]['size']:
            #    if diff < 0: # footnote index as superscript
            #        self.table['footer'] = self.table['bbox'][3]
            #    else: # probably actual footnote
            #        self.table['footer'] = chars[i]['bottom']
            #        separator.extend(footnote_separator)
            #    footnote_complete = not footnote_complete
            
        if footnote_complete == None: 
            separator.extend(footnote_separator)
            footnote_complete = True

        if header_separator == self.table['bbox'][1] and len(separator) > 0:
            header_separator = separator[0]['top']

        bbox = copy.copy(self.table['bbox'])
        bbox[3] = self.table['footer']
        self.clipping = self.clipping.crop(bbox)

        return footnote_complete, separator, header_separator if header_separator is not None else self.table['bbox'][1]
    
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

    def test_footnote(self):
        if len(self.table_lines) > 1:
            # test if the last segment is actually the footnote
            bbox = self.clipping.bbox.copy()
            bbox[1] = self.table_lines[-1]['bottom']
            bbox[3] = self.table['bbox'][3]
            c = self.clipping.crop(bbox).extract_words()
            w = c[0]['text'][0] + c[0]['text'][2] if len(c[0]['text']) > 2 else ""
            #test = self.find_columns(self.clipping.crop(bbox), x_space, symbols)
            if w == '()' or len(c[0]['text']) == 1:#len(test) == 0:
                self.table['footer'] = self.table_lines[-1]['bottom']

    def find_layout(self, x_space, y_space, symbols, ignore_footnote=False):
        self.test_footnote()

        bbox = self.clipping.bbox.copy()
        bbox[3] = self.table['footer']

        self.column_separator = []

        try: self.column_separator = [self.find_columns(self.clipping.crop(bbox), x_space, symbols)[0]] # get first column = row descriptor
        except: self.column_separator = []

        footnote_complete, self.row_separator, self.table['header'] = self.find_rows(self.clipping.crop(bbox), y_space)

        if not footnote_complete and not ignore_footnote: return footnote_complete, None, None

        col_sep = []
        
        # add table lines as row separator
        self.row_separator.extend([{'x0': self.table['bbox'][0], 'x1': self.table['bbox'][2], 'width': self.table['bbox'][2] - self.table['bbox'][0], 'object_type': 'line', 'top': x['top'], 'bottom': x['bottom']} for x in self.table['lines']])
        self.row_separator = sorted(self.row_separator, key=lambda e: e['top'])

        # table is separated in horizontal segments: the columns are individual for each segment (important for multi-header tables)
        # segments are defined by the top and bottom lines of the table, the header and the footer and the ruling lines above the headerline
        segments = [{'top': self.table['bbox'][1]}]
        segments.extend(self.table_lines.copy() if self.table['header'] == self.table['bbox'][1] else [x for x in self.table_lines.copy() if x['top'] < self.table['header']])
        if self.table['header'] != self.table['bbox'][1]: segments.append({'top': self.table['header'], 'bottom': self.table['header']})
        segments.extend([{'top': self.table['header'], 'bottom': self.table['header']}, {'top': self.table['footer'], 'bottom': self.table['footer']}])
        if self.table['footer'] != self.table['bbox'][3]: segments.append({'top': self.table['bbox'][3], 'bottom': self.table['bbox'][3]})

        i=0
        while i < len(segments)-1:
            bbox = self.clipping.bbox.copy()
            bbox[1] = segments[i]['top']
            bbox[3] = segments[i+1]['bottom']
            try: 
                cols = self.find_columns(self.clipping.crop(bbox), x_space, symbols)
            except: 
                i+=1
                continue

            col_sep.extend(cols)

            i+=1

        self.column_separator.extend(col_sep)

        return footnote_complete, self.column_separator, self.row_separator

    def get_table_settings(self):
        vertical_lines = [self.table['bbox'][0], self.table['bbox'][2]] # left and right line
        horizontal_lines = [self.table['bbox'][1], self.table['footer']] # top and bottom line
        #horizontal_lines.extend(self.table['lines'])
        if "column_separator" in vars(self).keys():
            vertical_lines.extend(self.column_separator)
        if "row_separator" in vars(self).keys():
            horizontal_lines.extend(self.row_separator)

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
    #im.draw_lines(tables[0]['lines'], stroke_width=3, stroke=(0,0,0))

    table_settings = le.get_table_settings()

    im.debug_tablefinder(table_settings)
    
    im.save('table.png')