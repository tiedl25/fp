import time
import __init__
from src.table_extractor import TableExtractor
from src.table_finder import TableFinder

import numpy as np
import os
import json
import pdfplumber
import concurrent.futures
from threading import Thread
from queue import Queue
import time

def getPdfPaths(path):
    pdfs = []
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.endswith(".pdf"):
                pdfs.append(os.path.join(root.lstrip(path), file))
    return pdfs

def extractAnnotatedTables(path, sub_start=0, sub_end=-1):
    test_dataset = []
    with open(path) as f:
        test_dataset = [json.loads(line) for line in f]
        
    test_dataset.sort(key = lambda e: e['filename'])
    if sub_start != 0 or sub_end != -1:  test_dataset = test_dataset[sub_start:sub_end]

    total = len(test_dataset)

    # group tables in examples json file by their filename and sort their coordinates to meet the requirements of pdfplumber
    test_tables_grouped = []

    for table in test_dataset:
        if len(test_tables_grouped) > 0 and table['filename'] == test_tables_grouped[len(test_tables_grouped)-1]['filename']:
            test_tables_grouped[len(test_tables_grouped)-1]['tables'].append({
                'bbox': table['bbox'],
                'cells': table['html']['cells']
                })
        else:
            test_tables_grouped.append({'filename': table['filename'], 'tables': [{'bbox': table['bbox'], 'cells': table['html']['cells']}]})

    return test_tables_grouped, total

def shrink_cell(page, cell):
    pagecrop = [x for x in page.crop(cell).chars if x['text'] not in [' ', '.']] # remove white spaces and dots because they should not be part of the cell

    b1 = min(pagecrop, key=lambda e: e['x0'], default={'x0': cell[0]})
    b2 = min(pagecrop, key=lambda e: e['top'], default={'top': cell[1]})
    b3 = max(pagecrop, key=lambda e: e['x1'], default={'x1': cell[2]})
    b4 = max(pagecrop, key=lambda e: e['bottom'], default={'bottom': cell[3]})

    return [b1['x0'], b2['top'], b3['x1'], b4['bottom']]

def compare_cells_by_bbox(table, test_table, pdf_path, t_i, page):
    if abs(len(table['cells']) - len(test_table['cells'])) < 20:
        return f"\t\t{pdf_path} Table {t_i+1}"

    return None

def test(pdf_paths, annotated_tables, draw=False, tol=5, only_bbox=False, find_method='rule-based'):
    i = 0
    match_list = []
    mismatch_list = []
    cell_match_list = []

    for pdf_path in pdf_paths:
        if i >= len(annotated_tables):
            break

        # Skip tables in one of both sets if they doesn't share the same filename
        if pdf_path != annotated_tables[i]['filename']:
            continue
        
        # compare only the bounding boxes or the whole tables including the cells
        if only_bbox:
            with pdfplumber.open(f"{dataset_path}/pdf/{pdf_path}") as pdf:
                page = pdf.pages[0]
                tableExtractor = TableFinder(page)
                try:
                    tables = tableExtractor.find_tables(left_threshold=10, right_threshold=5, bottom_threshold=9, top_threshold=4)
                except Exception as e:
                    print(e)
                    print(pdf_path)
                    continue
        else:
            try: 
                tableExtractor = TableExtractor(path=f"{dataset_path}/pdf/{pdf_path}", separate_units=False, find_method=find_method)
                tables = tableExtractor.extractTables(page_index=0) # all pdfs contain only one page
                page = tableExtractor.pages[0]
            except Exception as e:
                print(e)
                print(pdf_path)
                continue

        # Check if there are any tables at all
        if len(tables) == 0 and len(annotated_tables[i]['tables']) == 0:
            continue

        test_tables = annotated_tables[i]['tables']

        # reorder table and bbox coordinates to match the structure of pdfplumber
        for test_table in test_tables:
            bbox = test_table['bbox']
            bbox3 = bbox[3]
            bbox[3] = page.height - bbox[1]
            bbox[1] = page.height - bbox3

            test_table['bbox'] = bbox

            bboxs = []
            text = []

            for cell in test_table['cells']:
                if cell['tokens'] != []:
                    bboxs.append([cell['bbox'][0], page.height-cell['bbox'][3], cell['bbox'][2], page.height-cell['bbox'][1]])
                    text.append(''.join(cell['tokens']))
            
            test_table['cells'] = bboxs
            test_table['text'] = text
        
        # shrink cells of pdfplumber tables to smallest bounding box
        for table in tables:
            table_cells = []
            for x in table['cells']: 
                cell = shrink_cell(page, x)
                if list(x) == cell:
                    continue
                table_cells.append(cell)

            table['cells'] = table_cells

        match = True
        for t_i, table in enumerate(tables):
            for test_table in test_tables:
                # different criteria for matching
                assert_horizontal = abs(table['bbox'][1] - test_table['bbox'][1]) < tol and abs(table['bbox'][3] - test_table['bbox'][3]) < tol
                assert_vertical = abs(table['bbox'][0] - test_table['bbox'][0]) < tol and abs(table['bbox'][2] - test_table['bbox'][2]) < tol
                assert_all = np.allclose(table['bbox'], test_table['bbox'], atol=tol)
                assert_except_bottom = abs(table['bbox'][1] - test_table['bbox'][1]) < tol and abs(table['bbox'][2] - test_table['bbox'][2]) < tol and abs(table['bbox'][0] - test_table['bbox'][0]) < tol

                if assert_all:
                    match_list.append(f"\t{pdf_path} Table {t_i+1}")
                    if not only_bbox:
                        tmp = compare_cells_by_bbox(table, test_table, pdf_path, t_i, page)
                        if tmp != None: cell_match_list.append(tmp)
                    break   
            else:      
                mismatch_list.append(f"\t{pdf_path} Table {t_i+1}")
                match = False

        if draw and not match:
            im = page.to_image(resolution=300)
            im2 = page.to_image(resolution=300)
            for table in test_tables:
                im.draw_rect(table['bbox'], stroke_width=0, fill=(230, 65, 67, 65)) # red for test tables
                im.draw_rects(test_table['cells'], stroke_width=0, fill=(230, 65, 67, 65))

            for table in tables: 
                im2.draw_rect([table['bbox'][0], table['header'], table['bbox'][2], table['footer']], stroke_width=0)
                im2.draw_rects(table['cells'])

            im.save(f"img/{pdf_path.replace('/', '_')[0:-4]}_test.png")
            im2.save(f"img/{pdf_path.replace('/', '_')[0:-4]}.png")
            
        i+=1

    return match_list, mismatch_list, cell_match_list


def loading_sequence(queue):
    symbols = ['-', '\\', '|', '/']
    i = 0
    while True:
        time.sleep(1)
        print(f"{symbols[i % len(symbols)]} | {i} seconds", end='\r', flush=True)
        i += 1
        if queue.empty() == False:
            break

if __name__ == '__main__':
    s0 = time.time()

    # Start the loading sequence in a separate process
    q = Queue()
    loading_thread = Thread(target=loading_sequence, args=(q,))
    loading_thread.start()

    dataset_path = "fintabnet"
    pdf_paths = getPdfPaths(dataset_path + '/pdf')

    sub_start = 0
    sub_end = 50
    thread_number = 1
    
    annotated_tables, total = extractAnnotatedTables(dataset_path + "/FinTabNet_1.0.0_table_test.jsonl", sub_start=sub_start, sub_end=sub_end)   
    batch_size = int(total/thread_number)
    pdf_paths.sort()

    tol = 20
    thread = []
    total_matches = 0
    total_cell_matches = 0

    #test(pdf_paths, annotated_tables, draw=False, tol=tol, only_bbox=True)

    with concurrent.futures.ProcessPoolExecutor(max_workers=thread_number) as executor:
        matches = [executor.submit(test, pdf_paths, annotated_tables[i*batch_size:(i+1)*batch_size], tol=tol, draw=True, only_bbox=False, find_method='rule-based') for i in range(thread_number)]
        for m in matches:
            match_list, mismatch_list, cell_match_list = m.result()
            total_matches += len(match_list)
            total_cell_matches += len(cell_match_list)

    q.put(True)

    loading_thread.join()

    print(f"Matches: {total_matches}/{total}\t{total_matches/total*100} %")
    print(f"Cell Matches: {total_cell_matches}/{total_matches}\t{total_cell_matches/total_matches*100} %")

    s1 = time.time()
    print(f"{int((s1-s0) / 60)}:{int(s1-s0) % 60} minutes")