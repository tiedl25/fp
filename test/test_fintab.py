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

def extractAnnotatedTables(path, subset=None):
    test_dataset = []
    with open(path) as f:
        test_dataset = [json.loads(line) for line in f]
        
    
    test_dataset.sort(key = lambda e: e['filename'])
    if subset != None:  test_dataset = test_dataset[0:subset]

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

def test(pdf_paths, annotated_tables, draw=False, tol=5, only_bbox=False):
    i = 0
    match_list = []
    mismatch_list = []

    for pdf_path in pdf_paths:
        if i >= len(annotated_tables):
            break
        # Skip tables in one of both sets if they doesn't share the same filename
        if pdf_path != annotated_tables[i]['filename']:
            continue
        
        if only_bbox:
            with pdfplumber.open(f"{dataset_path}/pdf/{pdf_path}") as pdf:
                page = pdf.pages[0]
                tableExtractor = TableFinder(page)
                tables = tableExtractor.find_tables(left_threshold=10, right_threshold=5, bottom_threshold=9, top_threshold=4)
                
        else:
            tableExtractor = TableExtractor(path=f"{dataset_path}/pdf/{pdf_path}", separate_units=False)
            tables = tableExtractor.extractTables(page_index=0) # all pdfs contain only one page
            page = tableExtractor.pages[0]

        # Check if there are any tables
        if len(tables) > 0 or len(annotated_tables[i]['tables']) > 0:
            test_tables = annotated_tables[i]['tables']

            # reorder coordinates
            for test_table in test_tables:
                bbox = test_table['bbox']
                bbox3 = bbox[3]
                bbox[3] = page.height - bbox[1]
                bbox[1] = page.height - bbox3

            for t_i, table in enumerate(tables):
                for test_table in test_tables:
                    if np.allclose(table['bbox'], test_table['bbox'], atol=tol):
                        match_list.append(f"\t{pdf_path} Table {t_i+1}")
                        break   
                else:      
                    mismatch_list.append(f"\t{pdf_path} Table {t_i+1}")

            if draw:
                im = page.to_image(resolution=300)
                bboxs = [table['bbox'] for table in test_tables]
                im.draw_rects(bboxs, stroke_width=0, fill=(230, 65, 67, 65)) # red for test tables
                im.draw_rects([[x['bbox'][0], x['header'], x['bbox'][2], x['footer']] for x in tables], stroke_width=0)
                im.save(f"img/{pdf_path.replace('/', '_')[0:-4]}.png")
                
            i+=1

    return match_list, mismatch_list


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

    annotated_tables, total = extractAnnotatedTables(dataset_path + "/FinTabNet_1.0.0_table_test.jsonl", 500)   

    pdf_paths.sort()

    batch_size = 100
    tol = 20
    batches = int(total / batch_size)
    batches = 1 if batches < 1 else batches
    thread = []
    total_matches = 0

    with concurrent.futures.ProcessPoolExecutor() as executor:
        matches = [executor.submit(test, pdf_paths, annotated_tables[i*batch_size:(i+1)*batch_size], tol=tol, draw=False, only_bbox=True) for i in range(batches)]
        for m in matches:
            match_list, mismatch_list = m.result()
            total_matches += len(match_list)

    q.put(True)

    loading_thread.join()

    print(f"Matches: {total_matches}/{total}\t{total_matches/total*100} %")

    s1 = time.time()
    print(f"{int((s1-s0) / 60)}.{int(s1-s0) % 60} minutes")