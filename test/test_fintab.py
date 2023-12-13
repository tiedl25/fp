import __init__
from src.table_extractor import TableExtractor
from src.table_finder import TableFinder

import numpy as np
import os
import json
import pdfplumber
import threading
import concurrent.futures
import multiprocessing

def getPdfPaths(path):
    path = path + '/pdf'
    pdfs = []
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.endswith(".pdf"):
                pdfs.append(os.path.join(root.lstrip(path), file))
    return pdfs

def extractAnnotatedTables(path):
    test_dataset = []
    with open(f"{path}/FinTabNet_1.0.0_table_test.jsonl") as f:
        test_dataset = [json.loads(line) for line in f]
        
    
    test_dataset.sort(key = lambda e: e['filename'])
    #test_dataset = test_dataset[0:1000]

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

def test(pdf_paths, annotated_tables):
    matches = 0
    i = 0
    tol = 5

    for pdf_path in pdf_paths:
        if i >= len(annotated_tables):
            break
        # Skip tables in one of both sets if they doesn't share the same filename
        if pdf_path != annotated_tables[i]['filename']:
            continue
        
        #tableExtractor = TableExtractor(path=f"{dataset_path}/pdf/{pdf_path}", separate_units=False)
        #tables = tableExtractor.extractTables(page_index=0) # all pdfs contain only one page
        #page = tableExtractor.pages[0]

        with pdfplumber.open(f"{dataset_path}/pdf/{pdf_path}") as pdf:
            page = pdf.pages[0]
            tableExtractor = TableFinder(page)
            tables = tableExtractor.find_tables(left_threshold=20, right_threshold=20)

        # Check if there are any tables
        if len(tables) > 0 or len(annotated_tables[i]['tables']) > 0:
            #im = page.to_image(resolution=300)

            test_tables = annotated_tables[i]['tables']

            for test_table in test_tables:
                bbox = test_table['bbox']
                bbox3 = bbox[3]
                bbox[3] = page.height - bbox[1]
                bbox[1] = page.height - bbox3

            for t_i, table in enumerate(tables):
                match = False
                for test_table in test_tables:
                    #assert_horizontal = abs(table['bbox'][1] - test_tables[j]['bbox'][1]) < tol and abs(table['bbox'][3] - test_tables[j]['bbox'][3]) < tol

                    assert_all = np.allclose(table['bbox'], test_table['bbox'], atol=20)

                    if assert_all:
                        match = True
                        matches += 1                        

                #if not match:
                #    print(f"\t{pdf_path} Table {t_i+1}")
                #else:
                #    print(f"\t\t{pdf_path} Table {t_i+1}")

            #bboxs = [table['bbox'] for table in test_tables]
            #im.draw_rects(bboxs, stroke_width=0, fill=(230, 65, 67, 65)) # red for test tables
            #im.draw_rects([x['bbox'] for x in tables], stroke_width=0)
            #im.save(f"img/{pdf_path.replace('/', '_')[0:-4]}.png")
                
            i+=1

    return matches

if __name__ == '__main__':
    dataset_path = "fintabnet"
    pdf_paths = getPdfPaths(dataset_path)

    annotated_tables, total = extractAnnotatedTables(dataset_path)   

    pdf_paths.sort()

    print("Doesn't match:")

    batch_number = 500
    batches = int(total / batch_number)
    thread = []
    total_matches = 0

    #total_matches = test(pdf_paths, annotated_tables)

    with concurrent.futures.ProcessPoolExecutor() as executor:
        matches = [executor.submit(test, pdf_paths, annotated_tables[i*batch_number:(i+1)*batch_number]) for i in range(batches)]
        for m in matches:
            total_matches += m.result()

    #for i in range(batches):
    #    thread.append(multiprocessing.Process(target=test, args=(pdf_paths, annotated_tables[i*200:(i+1)*200],)))
    #    thread[i].start()
#
    #for t in thread:
    #    t.join()
    #    total_matches += t.result()

    print(f"Matches: {total_matches}/{total}\t{total_matches/total*100} %")