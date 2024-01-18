import argparse
import os

from ultralyticsplus import YOLO

from table_extractor import TableExtractor

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
    parser.add_argument("--find_method", dest="find_method", choices=["rule-based", "model-based"], default="rule-based", help="Choose if the table finding process should be a rule-based approach or with yolov8s table extraction. Default is rule-based.")
    parser.add_argument("--linepitch", dest="linepitch", choices=["avg", "min", "value"], help="Choose if to use automatic maximum linepitch either based on the average or the minimum linepitch in the pdf document or a custom value.", default="min")
    parser.add_argument("--max_linepitch", dest="max_linepitch", type=float, help="Choose a maximum for the line pitch until considered a new row. Default is 2", default=2)
    parser.add_argument("--max_charspace", dest="max_charspace", type=float, help="Choose a maximum for the space between characters until considered a new column. Default is 4", default=4)
    parser.add_argument("--img_path", dest="img_path", help="Directory for image to be saved to. Default is current working directory", default=".")
    parser.add_argument("--overwrite", dest="overwrite", action="store_true", help="Overwrite existing images with the same filename", default=False)

    # parse the arguments
    args = parser.parse_args()
    files = getPdfPaths(args.path) if os.path.isdir(args.path) else [args.path]

    if args.find_method == 'model-based':
        # load model
        model = YOLO('keremberke/yolov8s-table-extraction')

        # set model parameters
        model.overrides['conf'] = 0.25  # NMS confidence threshold
        model.overrides['iou'] = 0.45  # NMS IoU threshold
        model.overrides['agnostic_nms'] = False  # NMS class-agnostic
        model.overrides['max_det'] = 10  # maximum number of detections per image
    else:
        model = None    

    for file in files:
        print(file)
        te = TableExtractor(path=file, separate_units=False, find_method=args.find_method, model=model, determine_row_space=args.linepitch, max_column_space=args.max_charspace, max_row_space=args.max_linepitch)
        tables = te.extractTables(img_path=args.img_path, overwrite=args.overwrite)

