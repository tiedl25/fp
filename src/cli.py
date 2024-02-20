#!/usr/bin/env python3
import argparse
import os

from table_extractor import TableExtractor
from transformers import AutoImageProcessor, TableTransformerForObjectDetection

def getPdfPaths(path):
    pdfs = []
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.endswith(".pdf"):
                pdfs.append(os.path.join(root, file))
    return pdfs
 
if __name__ == "__main__":
    # create parser
    parser = argparse.ArgumentParser()
    
    # add arguments to the parser
    parser.add_argument("path", help="Path to pdf file or directory containing pdf files")
    parser.add_argument("--detection_method", dest="detection_method", choices=["rule-based", "model-based"], default="rule-based", help="Choose if the table detection should be a rule-based approach or with microsofts table extraction. Default is rule-based.")
    parser.add_argument("--layout_method", dest="layout_method", choices=["rule-based", "model-based"], default="rule-based", help="Choose if the table layout detection should be a rule-based approach or with microsofts table extraction. Default is rule-based.")
    parser.add_argument("--max_linespace", dest="max_linespace", type=float, help="Choose a maximum for the line space until considered a new row. Default is -0.3", default=-0.3)
    parser.add_argument("--max_charspace", dest="max_charspace", type=float, help="Choose a maximum for the space between characters until considered a new column. Default is 5", default=5)
    parser.add_argument("--img_path", dest="img_path", help="Directory for image(s) to be saved to. Default is current working directory", default=".")
    parser.add_argument("--overwrite", dest="overwrite", action="store_true", help="Overwrite existing images that have the same filename", default=False)

    # parse the arguments
    args = parser.parse_args()
    files = getPdfPaths(args.path) if os.path.isdir(args.path) else [args.path]

    if args.detection_method == 'model-based':
        image_processor = AutoImageProcessor.from_pretrained("microsoft/table-transformer-detection")
        model = TableTransformerForObjectDetection.from_pretrained("microsoft/table-transformer-detection")
    else:
        model = None
        image_processor = None

    if args.layout_method == 'model-based':
        structure_image_processor = AutoImageProcessor.from_pretrained("microsoft/table-transformer-structure-recognition")
        structure_model = TableTransformerForObjectDetection.from_pretrained("microsoft/table-transformer-structure-recognition")
    else:
        structure_model = None
        structure_image_processor = None

    for file in files:
        print(file)
        te = TableExtractor(path=file, separate_units=False, detection_method=args.detection_method, layout_method=args.layout_method, model=model, image_processor=image_processor, layout_model=structure_model, layout_processor=structure_image_processor, max_column_space=args.max_charspace, max_row_space=args.max_linespace)
        tables = te.extractTables(img_path=args.img_path, overwrite=args.overwrite)

