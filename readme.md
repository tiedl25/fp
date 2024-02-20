# Internship: Table detection with ruling lines

Name: Max Tiedl

Matriculation Number: 4187550

Semester: 7

Advisor Nicolas Reuter

# Introduction
The goal of this internship is to detect tables within pdfs, based on their ruling lines. The table-formatting solely with ruling lines is relatively common in financial reports. The method is rule-based and gives therefore more control over the output. Rules can be easily implemented and the results can be easily understood. Nevertheless not every edge case can be covered.

| <img src="assets/example.png" width="600" /> | 
|:--:| 
| *Example of a table with ruling lines* |

# Tasks
There are three major steps to be solved: the table detection, the layout detection and the table extraction which combines the first and second step and involves some postprocessing. To develop and test the programm the [Fintabnet dataset](https://dax-cdn.cdn.appdomain.cloud/dax-fintabnet/1.0.0/data_preview/index.html) is used. To analyse and extract certain objects (chars, lines, etc.) from the pdfs the python package [pdfplumber](https://github.com/jsvine/pdfplumber) is used.

## Table detection
### Rule-based Approach
#### Getting the table lines
All lines are extracted with [pdfplumber](https://github.com/jsvine/pdfplumber), vertical lines are ignored.

#### Concatenate Lines
The number of lines found in the tables is often higher, than the number of lines visually present in the pdf. The first consideration was that dashed lines are presented with multiple small lines, but instead many long lines are separated into multiple parts for no obvious reason. The lines are concatenated based on their distance to the top of the page. The difference on the x-axis is not taken into consideration because, it gives better results for the table finding process per se. Nevertheless the information about the different line segments, where the x-difference matters is also stored.

#### Special lines
Some lines are not detected by pdfplumber because they show up as filled rectangles with very little height. They are also considered for table detection. 
For some pdfs it was also helpful to consider dot sequences as lines. Such sequences can be seen in the folloging image.

| <img src="assets/dot_lines.png" width="300" /> | 
|:--:| 
| *Sequences of dots* |

#### Getting the bounding box
Each line is considered a new table. Starting from this line, two bounding boxes are created, one above the line and one below. They are open to the top or bottom respectively. The left and right border are the start and end point of the ruling line.
The next step is to sort the characters in each bounding box by their distance to the top of the page. If the y-difference between two characters is greater than a specified value, a new top or bottom border is set. 
With this new bounding box the same process is repeated for the left and right side. 
The resulting bounding boxes are compared to find overlapping bounding boxes. All overlapping bounding boxes are merged by adjusting the bounding box.

| <img src="assets/find_bbox.png" width="300" /> | <img src="assets/individual_bboxs.png" width="300" /> | 
|:--:|:--:|
| *Find the bounding box starting with a ruling line* | *Merging the individual tables, found with ruling lines* |

#### Page Layout
If the page has a single column layout, the threshold for the left and right is ignored and instead the most left and right characters are used as border for the table. Characters that are rotated, which can be obtained with their matrix that pdfplumber provides, are ignored. The following picture shows an example that demonstrates the necessity. The most right character would be one of the characters inside the black box, which would break the layout detection.
Also all lines wider than half of the page are ignored for table detection when a two column layout is detected
A page is considered a one-column page if characters and lines can be found in the middle of the page. Two cases are considered:
+ The object height of each object found within the bounding box (mid, top, mid+3, bottom) is summed up. If this height is greater than 30% of the page height we consider it a one-column layout
+ The bounding box is set to (mid, top of table, mid+3, bottom of table). If any characters or lines are found, the page is also considered a one-column page.

### Model-based Approach
For comparison and better results, two different machine-learning models are used. [yolov8s-table-extraction](https://huggingface.co/keremberke/yolov8s-table-extraction) and [microsoft-table-detection](https://github.com/microsoft/table-transformer). The settings for microsofts table-detection are slightly altered to recognize more tables with the cost of a little more inacuracy. The default threshold value is 0.9, but with that a lot of tables are not detected. With a threshold value of 0.5 a lot more tables are detected but they sometimes have to wide boundaries, especially to the top and bottom. However this can be compensated within the table layout detection. Overall Microsofts model gives better results. Both approaches are implemented within the table detection class and the user can choose what method should be used. The image data both models need are accessed via pdfplumber.

## Layout detection
### pdfplumber table extraction
Pdfplumber has it is own method for table extraction, with options to specify explicit lines. Unfortunately the lack of information about the tables lead to no results. The ruling lines do not really help, but the results are better when the bounding box from the first step ist used.

To detect the layout it uses the distance between words and characters for both column and row detection. But even after tweaking the settings the table extraction is not very reliable. The row detection is good but columns are often divided into multiple columns.

| <img src="assets/pdfplumber_table_extraction.png" width="300" /> | 
|:--:| 
| *Table extraction with pdfplumber* |

### Custom approach
To have more control over the column/row detection and to implement custom rules, a rule-based approach is presented. This approach comes down to finding rows and columns. The separators for these rows/columns are then used as explicit lines for pdfplumber's table extraction.
The very basic decision criteria for the separators is the x-distance between to characters for vertical and the y-distance for horizontal lines respectively. For both axis a threshold can be set. The default settings are x=5, y=-0.3. The threshold for row detection has to be slightly negative because some lines overlap a little because characters like brackets or superscripts.

#### Average line spacing (deprecated)
To improve the separation of different rows, the maximum line spacing from which a new row is created, is calculated based on the text in the pdf rather than a default value. Line spacing is calculated as the y-distance between 2 characters. By skipping negative values, characters one the same text line are ignored. The average line spacing can be calculated with the mode() function of the statistics library. However it turned out, that the minimum line spacing (staticstics.min()) gives overall better results. The user can change this and also set a custom value.

This method is deprecated: The initial goal here was to distinguish between separate rows and continuous text over multiple rows. This turned out to be impossible only with line spacing.

#### Font change
In the image below the first two columns are not separated. We can lower the threshold but that also creates more separators, that we do no want. So instead another criteria is introduced. The font name, which can be easily retrieved for each character with pdfplumber. When the font changes and the x-distance is greater than 3 a separator is added. The minimum x-distance as second dependency is required. In some tables the first column also has a bold header (changes the font name). Without the minimum x-distance multiple separator lines would be created.

| <img src="assets/font_criteria.png" width="300" /> | <img src="assets/font_criteria_exception.png" width="300" /> |
|:--:|:--:|
| *Separate column when the font changes* | *A minimum threshold is still important* |



#### Footnotes (and text-lines that should be excluded)
Footnotes below the actual table are another problem to consider. Not so much with the machine learning models but with the custom approach for table detection. However the models also suffer from text-lines that should not belong to the table.
Footnotes are recognized as such, if they meet the following requirements:
    + The line in the table consists of 2 cells
    + the first cell contains an index number like a number in brackets, or a number followed by a dot
    + the first cell is not wider than 10% of the table
The search for footnotes starts from the bottom and ends with the first line that is not a footnote.
Other lines that should not be part of the table are lines with no vertical divider (only one cell), that beginn within the first 10% of the table width. They are removed both above and below the table

| <img src="assets/remove_at_bottom.png" width="600" /> | <img src="assets/remove_footnote.png" width="600" /> |
|:--:|:--:|
| *Continuous text is ignored* | *Footnotes are ignored* |

#### Header
Unfortunately the ruling lines are rather useless for consistent header extraction. 
Instead the header separator, is set to be the first occurrence of a font-change between two characters, assuming they are sorted from top to bottom. The font change has to be in the upper part of the table. This is calculated by $(1-tableHeight)/pageHeight * 0.9$. A font change below this line isn't considered. This means for bigger tables the font change has to be in a higher part of the table than for smaller tables. 

#### Column separation with header line
To correctly recognize multi header tables, the table is divided into multiple horizontal segments. The body (everything except the header) is a segment and every row in the header is a segment. The column detection is performed for every segment individually.

Every detected column separator is tested, if it can be extended to the top. For that a small bounding box that covers the are above the detected column separator is created. If any object (character, ruling line) intersects with this bounding box, the highest point, that does not intersect with the lowest object is the new top of the column. If none could be found, the upper boundary of the table is the new top.

| <img src="assets/multi_header.png" width="600" /> | 
|:--:| 
| *Multi-Header Table* |

## Table Extraction
The table extraction combines the table detection and the layout detection. After that some postprocessing is done (remove cells, merge, cells, shrink cells).

### Remove Cells
Cells are removed if they either have only one cell, one column or one row.

### Merge cells
#### Cells in the body
Cells in the body are merged with the underlying cell, if:
+ they are the only cell in the row
+ they do not end with a colon or a dot sequence
+ there is no font change between both cells

#### Rows in the header
Underlying rows in the header are merged, when they share the same layout and do not have ruling lines in between.

#### Cells containing only dollar symbol

### Shrink Cells
Remove dots and spaces and then shrink extracted cells to the minimum bounding box.


# Testing and Evaluation
The test_fintab.py script evaluates if the tables being detected in a pdf correspond to the tables in the fintabnet dataset. Both the custom table detection and microsofts table detection were tested. The dataset can be downloaded from <https://developer.ibm.com/exchanges/data/all/fintabnet/>. <br>
For every detected table a similar table in fintabnet is looked for (threshold 30). That means, the summed up differences of each side are required to be less than 30. If that is the case, the table cells are compared. To check whether two cells match is tested with the SequenceMatcher class (difflib library). If the matching ratio is greater than 0.9, they are considered similar enough. With all cells compared, the precision, recall and f1 score are calculated for the table. If the f1 score is greater than 0.7 the cell structure is considered equal enough. The choosen values have turned out to be a good compromise. For comparison the following images shows what would be considered incorrect if we want a perfect table.

| <img src="assets/cell_compare_no_threshold.png" width="600" /> | <img src="assets/cell_compare_no_threshold_test.png" width="600" /> |
|:--:|:--:|
| *Classified as false (with 100% cell coverage)* | *Annotated table in fintabnet* |

Comparison between the custom approach and the microsofts table detection model. Both use the same batch of the first 10000 tables sorted alphabetically by their filename.

Metric | Custom table detection | % | Microsoft table detection with custom layout detection | % | Microsoft table detection + layout detection | % 
---|---|---|---|---|---|---
Number of tables found | 10135/10000 | - | 8366/10000 | - | 8417/10000 | - 
Precision (Number of matches / Number of found tables) | 7876/10135 | 77.71 % | 7093/8366  | 84.78 % | 6961/8417 | 82.7 % 
Recall (Number of matches / Number of expected tables) | 7876/10000 | 78.76 % | 7093/10000 | 70.93 % | 6961/10000 | 69.61 %
F1-Score | 0.782 | - | 0.772 | - | 0.756 | - 
Cell Precision (Number of tables with correct cells / Number of found Tables) | 7152/10135 | 70.57 % | 6290/8366 | 75.19 % | 3372/8417 | 40.06 % 
Cell Recall (Number of tables with correct cells / Number of expected tables) | 7152/10000 | 71.52 % | 6290/10000 | 62.9 % | 3372/10000 | 33.72 %
Cell F1-Score | 0.71 | - | 0.685 | - | 0.366 | -
Mean Cell F1-Score | 0.91 | - | 0.898 | - | 0.653 | - 
Number of tables with correct cells / Number of correct tables | 7152/7876 | 90.81 % | 6290/7093 | 88.68 % | 3372/6961 | 48.44 % 
Time spent | 13:47 minutes * | - | 128:46 minutes ** | - | 159:19 minutes ** | - 

\* with parallelization: 10 workers with maximum of 50 tasks until new worker is spawned

\** no cuda-capable gpu -> calculations on the cpu 

# Outlook
## Header

## Problems
### The fintabnet dataset is inconsistent

| <img src="assets/fintab_false_annotated.png" width="300" /> | <img src="assets/fintab_false_annotated2.png" width="300" /> | <img src="assets/fintab_false_cells.png" width="300" /> |
|:--:|:--:|:--:|
| *Tables alse incorrectly annotated* | *Tables alse incorrectly annotated* | *Cell have incorrect bounding boxes* |

### Cli
<img src="assets/cli.png" />


Table of Contents

1. [Internship: Table detection with ruling lines](#internship-table-detection-with-ruling-lines)
2. [Introduction](#introduction)
3. [Tasks](#tasks)
    1. [Table detection](#table-detection)
        1. [Rule-based Approach](#rule-based-approach)
            1. [Getting the table lines](#getting-the-table-lines)
            2. [Concatenate Lines](#concatenate-lines)
            3. [Special lines](#special-lines)
            4. [Getting the bounding box](#getting-the-bounding-box)
            5. [Page Layout](#page-layout)
        2. [Model-based Approach](#model-based-approach)
    2. [Layout detection](#layout-detection)
        1. [pdfplumber table extraction](#pdfplumber-table-extraction)
        2. [Custom approach](#custom-approach)
            1. [Average line spacing (deprecated)](#average-line-spacing-deprecated)
            2. [Font change](#font-change)
            3. [Footnotes (and text-lines that should be excluded)](#footnotes-and-text-lines-that-should-be-excluded)
            4. [Header](#header)
            5. [Column separation with header line](#column-separation-with-header-line)
    3. [Table Extraction](#table-extraction)
        1. [Remove Cells](#remove-cells)
        2. [Merge cells](#merge-cells)
            1. [Cells in the body](#cells-in-the-body)
            2. [Rows in the header](#rows-in-the-header)
            3. [Cells containing only dollar symbol](#cells-containing-only-dollar-symbol)
        3. [Shrink Cells](#shrink-cells)
4. [Testing and Evaluation](#testing-and-evaluation)
5. [Outlook](#outlook)
    1. [Header](#header)
    2. [Problems](#problems)
        1. [The fintabnet dataset is inconsistent](#the-fintabnet-dataset-is-inconsistent)
        2. [Cli](#cli)


