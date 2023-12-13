import __init__
from src.table_extractor import TableExtractor

import numpy as np
import os
import json

if __name__ == '__main__':
    path = "examples/pdf/FDX/2017"
    files = os.listdir(path)

    with open('examples/examples.jsonl') as f:
        test_dataset = [json.loads(line) for line in f]
        test_dataset.sort(key = lambda e: e['filename'])

    page_height = 792

    # group tables in examples json file by their filename and sort their coordinates to meet the requirements of pdfplumber
    test_tables_grouped = []

    for table in test_dataset:
        bbox = table['bbox']
        bbox3 = bbox[3]
        bbox[3] = page_height - bbox[1]
        bbox[1] = page_height - bbox3

        if len(test_tables_grouped) > 0 and table['filename'] == test_tables_grouped[len(test_tables_grouped)-1]['filename']:
            test_tables_grouped[len(test_tables_grouped)-1]['tables'].append({
                'bbox': table['bbox'],
                'cells': table['html']['cells']
                })
        else:
            test_tables_grouped.append({'filename': table['filename'], 'tables': [{'bbox': table['bbox'], 'cells': table['html']['cells']}]})

    files.sort()

        # Metrics
    matches = 0
    total = len(test_dataset)

    print("Doesn't match:")

    test_table_index = 0
    tol = 5

    for file in files:
        # Skip tables in one of both sets if they doesn't correspond to each other
        while int(file[-6:-4]) > int(test_tables_grouped[test_table_index]['filename'][-6:-4]):
            test_table_index+=1
        if int(file[-6:-4]) < int(test_tables_grouped[test_table_index]['filename'][-6:-4]):
            continue

        te = TableExtractor(path=f"{path}/{file}", separate_units=False)
        tables = te.extractTables(page_index=0)
        page = te.pages[0]

        if len(tables) > 0 or len(test_tables_grouped[test_table_index]['filename']) > 0:
            im = page.to_image(resolution=300)

            test_tables = test_tables_grouped[test_table_index]['tables']

            for i in range(len(tables)):
                match = False
                for j in range(len(test_tables)):
                    assert_horizontal = abs(tables[i]['bbox'][1] - test_tables[j]['bbox'][1]) < tol and abs(tables[i]['bbox'][3] - test_tables[j]['bbox'][3]) < tol
                    b = tables[i]['bbox']
                    b[1] == tables[i]['header']
                    b[3] == tables[i]['footer']
                    assert_all = np.allclose(tables[i]['bbox'], test_tables[j]['bbox'], atol=5)

                    if assert_all:
                        match = True
                        matches += 1

                        import functools
                        import operator
                        words = functools.reduce(operator.iconcat, tables[i]['text'], [])

                        test_words = []
                        for test_cell in test_tables[j]['cells']:
                            test_words.append(''.join(test_cell['tokens']))

                        first_set = set(words)
                        sec_set = set(test_words)
                        # Get the differences between two sets
                        differences = (first_set - sec_set).union(sec_set - first_set)

                        if len(differences) > 0:
                            print(f"\t\t{file} Table {i+1}")
                            print(f"\t\tDifferences: {differences}")
                        

                if not match:
                    print(f"\t{file} Table {i+1}")
            
            bboxs = [table['bbox'] for table in test_tables]
            im.draw_rects(bboxs, stroke_width=0, fill=(230, 65, 67, 65))
            im.draw_rects([x['bbox'] for x in tables], stroke_width=0)
            im.save(f"img/{file[0:-4]}.png")
            test_table_index+=1
        
    print(f"Matches: {matches}/{total}\t{matches/total*100} %")