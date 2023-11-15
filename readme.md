To develop and test the programm currently the FINTAB example dataset is used.

### Progress

#### Concatenate Lines
I first started getting all the lines that are present in a pdf document. That is relatively easy with the pdfplumber package. Interesting was that it showed many more lines, than there were visually present in the pdf. So at first I thought, the dashed lines were consisting of multiple single lines, but that turned out to be false. Instead the long lines of the table were separated into multiple parts, partly representing the size of a column. I say partly because there were also lines overlapping, that could present the different indentation in a row, but that wasn't very clear. I decided to go another way to later divide the table in columns.
To further process the lines, I wrote a method that concatenates all lines with the same distance to the top of the page.

#### Getting the bounding box
Each ruling line represents at first a table and is it's anker point. Starting from there I create two bounding boxes one above the line and one below. They are open to the top or bottom respectively. The left and right border are represented by two horizontal lines. The distance to the left side of the page is the start or end point of the ruling line.
The characters in each bounding box are sorted by their distance to the top of the page. If the y-difference between two characters is greater than a specified value, we set a new top or bottom border. Both bounding boxes are combined and present the new bounding box of the table. 
Now we look for overlapping tables and merge them together by adjusting the bounding box.


#### Problems
+ Not every table in the pdfs is given in the annotated json file
+ Some tables don't consist of any line



### Installation
Coming soon ...
    