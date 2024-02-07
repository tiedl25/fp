import time
import __init__
from src.table_extractor import TableExtractor
from src.table_finder import TableFinder

from ultralyticsplus import YOLO, render_result
from difflib import SequenceMatcher

from transformers import AutoImageProcessor, TableTransformerForObjectDetection

import numpy as np
import os
import json
import pdfplumber
import concurrent.futures
from threading import Thread
from queue import Queue
import time
import shutil

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
        if len(test_tables_grouped) > 0 and table['filename'] == test_tables_grouped[-1]['filename']:
            test_tables_grouped[-1]['tables'].append({
                'bbox': table['bbox'],
                'cells': table['html']['cells']
                })
        else:
            test_tables_grouped.append({'filename': table['filename'], 'tables': [{'bbox': table['bbox'], 'cells': table['html']['cells']}]})

    return test_tables_grouped, total

def compare_cells(table, test_table, pdf_path, t_i, page):
    matches = 0
    for cell in table['cells']:
        for test_cell in test_table['cells']:
            s = SequenceMatcher(None, test_cell['text'], cell['text'])
            if s.ratio() > 0.7:
                matches += 1
                break

    if matches > len(test_table['cells']) - 5:
        return f"\t\t{pdf_path} Table {t_i+1}"

    return None

def test(pdf_paths, annotated_tables, draw='cell_match', tol=5, only_bbox=False, find_method='rule-based'):
    try: 
        shutil.rmtree("img")
    except: pass
    os.mkdir("img")
    if find_method == 'model-based':
        # load model
        model = YOLO('keremberke/yolov8s-table-extraction')

        # set model parameters
        model.overrides['conf'] = 0.25  # NMS confidence threshold
        model.overrides['iou'] = 0.45  # NMS IoU threshold
        model.overrides['agnostic_nms'] = False  # NMS class-agnostic
        model.overrides['max_det'] = 1000  # maximum number of detections per image
        image_processor = None
    elif find_method == 'microsoft':
        image_processor = AutoImageProcessor.from_pretrained("microsoft/table-transformer-detection")
        model = TableTransformerForObjectDetection.from_pretrained("microsoft/table-transformer-detection")

    i = 0
    match_list = []
    mismatch_list = []
    cell_match_list = []
    total_found_tables = 0

    for pdf_path in pdf_paths:
        if i >= len(annotated_tables):
            break

        while pdf_path > annotated_tables[i]['filename']:
            i += 1

        # Skip tables in one of both sets if they doesn't share the same filename
        if pdf_path < annotated_tables[i]['filename']:
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
                tableExtractor = TableExtractor(path=f"{dataset_path}/pdf/{pdf_path}", separate_units=False, find_method=find_method, model=model, image_processor=image_processor, determine_row_space="min", max_column_space=4, max_row_space=2)
                tables = tableExtractor.extractTables(page_index=0) # all pdfs contain only one page
                page = tableExtractor.pages[0]
            except Exception as e:
                print(e)
                print(pdf_path)
                continue

        test_tables = annotated_tables[i]['tables']

        # reorder table and bbox coordinates to match the structure of pdfplumber
        for test_table in test_tables:
            bbox = test_table['bbox']
            bbox3 = bbox[3]
            bbox[3] = page.height - bbox[1]
            bbox[1] = page.height - bbox3
            test_table['bbox'] = bbox

            test_table_cells = []
            for cell in test_table['cells']:
                if 'bbox' not in cell.keys():
                    continue
                bbox = [cell['bbox'][0], page.height-cell['bbox'][3], cell['bbox'][2], page.height-cell['bbox'][1]]
                try: text = page.crop(bbox).extract_text().replace('\n', ' ')
                except Exception as e:
                    print(e)
                    print(pdf_path)
                    continue
                test_table_cells.append({'bbox': bbox, 'text': text})
            test_table['cells'] = test_table_cells

        match = True
        cell_match = True
        for t_i, table in enumerate(tables):
            total_found_tables += 1
            for test_table in test_tables:
                # different criteria for matching
                assert_horizontal = abs(table['bbox'][1] - test_table['bbox'][1]) < tol and abs(table['bbox'][3] - test_table['bbox'][3]) < tol
                assert_vertical = abs(table['bbox'][0] - test_table['bbox'][0]) < tol and abs(table['bbox'][2] - test_table['bbox'][2]) < tol
                b = table['bbox'].copy()
                b[3] = table['footer']
                assert_all = np.allclose(b, test_table['bbox'], atol=tol)
                assert_except_bottom = abs(table['bbox'][1] - test_table['bbox'][1]) < tol and abs(table['bbox'][2] - test_table['bbox'][2]) < tol and abs(table['bbox'][0] - test_table['bbox'][0]) < tol

                if assert_all:
                    match_list.append(f"\t{pdf_path} Table {t_i+1}")
                    if not only_bbox:
                        tmp = compare_cells(table, test_table, pdf_path, t_i, page)
                        if tmp != None: cell_match_list.append(tmp)
                        else: cell_match = False
                    break   
            else:      
                mismatch_list.append(f"\t{pdf_path} Table {t_i+1}")
                match = False
        
        if len(tables) == 0: 
            match = False
            cell_match = False

        if (draw=='cell_match' and match and not cell_match) or (only_bbox and draw=='cell_match' and not match):
            im = page.to_image(resolution=300)
            im2 = page.to_image(resolution=300)
            for table in test_tables:
                im.draw_rect(table['bbox'], stroke_width=0, fill=(230, 65, 67, 65)) # red for test tables
                if not only_bbox: im.draw_rects([x['bbox'] for x in table['cells']], stroke_width=0, fill=(230, 65, 67, 65))

            for table in tables: 
                im2.draw_rect(table['bbox'], stroke_width=0) # [table['bbox'][0], table['header'], table['bbox'][2], table['footer']], stroke_width=0)
                if not only_bbox: im2.draw_rects([x['bbox'] for x in table['cells']])

            im.save(f"img/{pdf_path.replace('/', '_')[0:-4]}_test.png")
            im2.save(f"img/{pdf_path.replace('/', '_')[0:-4]}.png")

        if draw=='bbox_match' and not match:
            im = page.to_image(resolution=300)
            for table in test_tables:
                im.draw_rect(table['bbox'], stroke_width=0, fill=(230, 65, 67, 65)) # red for test tables

            for table in tables: 
                im.draw_rect([table['bbox'][0], table['bbox'][1], table['bbox'][2], table['footer']], stroke_width=0)
                #im.draw_hline(table['footer'])


            im.save(f"img/{pdf_path.replace('/', '_')[0:-4]}.png")
            
        i+=1

    return match_list, mismatch_list, cell_match_list, total_found_tables

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

    sub_start = 2000
    sub_end = -1
    thread_number = 4
    
    annotated_tables, total = extractAnnotatedTables(dataset_path + "/FinTabNet_1.0.0_table_test.jsonl", sub_start=sub_start, sub_end=sub_end)   
    batch_size = int(total/thread_number)
    pdf_paths.sort()

    tol = 30
    thread = []
    total_matches = 0
    total_mismatches = 0
    total_cell_matches = 0
    total_found_tables = 0

    match_list, mismatch_list, cell_match_list, total_found_tables = test(pdf_paths, annotated_tables, tol=tol, draw='bbox_match', only_bbox=False, find_method='microsoft')
    total_matches = len(match_list)
    total_mismatches = len(mismatch_list)
    total_cell_matches = len(cell_match_list)

    #mmlist = []
    #mlist = []
    #clist = []
#
    #with concurrent.futures.ProcessPoolExecutor(max_workers=thread_number) as executor:
    #    matches = [executor.submit(test, pdf_paths, annotated_tables[i*batch_size:(i+1)*batch_size], tol=tol, draw='bbox_match', only_bbox=False, find_method='microsoft') for i in range(thread_number)]
    #    for m in matches:
    #        match_list, mismatch_list, cell_match_list, tft = m.result()
    #        mmlist.extend(mismatch_list)
    #        mlist.extend(match_list)
    #        clist.extend(cell_match_list)
    #        total_matches += len(match_list)
    #        total_mismatches += len(mismatch_list)
    #        total_cell_matches += len(cell_match_list)
    #        total_found_tables += tft

    q.put(True)

    loading_thread.join()

    precision = total_matches / total_found_tables
    recall = total_matches / total
    cell_precision = total_cell_matches / total_found_tables
    cell_recall = total_cell_matches / total

    print(f"Number of tables found: {total_found_tables}/{total}")
    print(f"Precision:\t{total_matches}/{total_found_tables}\t{round(precision*100, 2)} %")
    print(f"Recall:\t{total_matches}/{total}\t{round(recall*100, 2)} %")
    print(f"F1-Score:\t{round((2*precision*recall)/(precision+recall), 2)}")
    print(f"True positive with correct cells:\t\t{total_cell_matches}/{total_matches}\t{round(total_cell_matches/total_matches*100, 2)} %")
    print(f"True positive with correct cells overall:\t{total_cell_matches}/{total_found_tables}\t{round(total_cell_matches/total_found_tables*100, 2)} %")
    print(f"Cell F1-Score:\t{round((2*cell_precision*cell_recall)/(cell_precision+cell_recall), 2)}")

    s1 = time.time()
    print(f"{int((s1-s0) / 60)}:{int(s1-s0) % 60} minutes")