To develop and test the programm currently the FINTAB example dataset is used. To analyse and extract certain objects from the pdfs the pdfplumber python package is used

## Progress

#### Concatenate Lines
I first started getting all the lines that are present in a pdf document. That is relatively easy with the pdfplumber package. Interesting was that it showed many more lines, than there were visually present in the pdf. So at first I thought, the dashed lines were consisting of multiple single lines, but that turned out to be false. Instead the long lines of the table were separated into multiple parts, partly representing the size of a column. I say partly because there were also lines overlapping, that could present the different indentation in a row, but that wasn't very clear. I decided to go another way to later divide the table in columns.
To further process the lines, I wrote a method that concatenates all lines with the same distance to the top of the page.

#### Getting the bounding box
Each ruling line represents at first a table and is it's anker point. Starting from there I create two bounding boxes one above the line and one below. They are open to the top or bottom respectively. The left and right border are represented by two horizontal lines. The distance to the left side of the page is the start or end point of the ruling line.
The characters in each bounding box are sorted by their distance to the top of the page. If the y-difference between two characters is greater than a specified value, we set a new top or bottom border. The same is now also done for left and right. All bounding boxes are combined and present the new bounding box of the table. 
Now we look for overlapping tables and merge them together by adjusting the bounding box.

<img src="assets/find_bbox.png" title="Find bbox border (top, bottom, left, right)" alt="" width="300" />
<img src="assets/individual_bboxs.png" width="300" />

### Cell Extraction
#### pdfplumber table extraction
Pdfplumber has it's own method for table extraction. I tried to use it in the beginning, but the lack of information about the tables lead to no results. The only given information are the ruling lines, which are not really of any help.
The situation changes with the given bounding box. No we can provide the outline of the table as explicit horizontal/vertical lines in the tablesettings. The method that is used besides that is "text" for both column and rows. 
The results are not what I hoped for and even after tweaking the settings a littel more it is better but not we want for reliable table extraction

<img src="assets/pdfplumber_table_extraction.png" width="300" />

#### LayoutExtractor
With a new class LayoutExtractor I develop a custom approach to get separator lines for columns and rows. These are then used in pdfplumber as explicit lines for cell extraction.
The very basic decision criteria for the separators is the x-distance between to characters for vertical and the y-distance for horizontal lines respectively. For both axis a threshold can be set. the default settings by now are x=5, y=2. Ofcourse there are also some edge cases

<img src="assets/font_criteria.png" width="300" />

In this example the first and second column are not separated. We can lower the x value but that also creates more separator, that we don't want. So instead another criteria is introduced. The font name, which can be easily retrieved for each character with pdfplumber. When the font changes and the x-distance is greater than 1 we also create a new separator. The minimum x-distance is required. In some tables the first column also has a bold header (changes the font name). Without the minimum x-distance multiple separator lines would be created.

<img src="assets/font_criteria_exception.png" width="300" />

Another problem are footnotes. I first thought of completely removing them from the table extraction, but they are important information. So the table needs to be divided into the actual table and the bounding box for the footnotes. That is done in the method for saparting row. The first approach was to use the font size to distinguish between the table and the footnotes. But the footnote numbers appear ofcourse also directly in the table as superscripts. I even thought about the transformation matrix of the characters but that was a dead end.



### Problems
+ Not every table in the pdfs is given in the annotated json file
+ Some tables don't consist of any line
+ The maximum differences are difficult to assign generally
