from typing import Generator, List, Optional
import marko
from marko.md_renderer import MarkdownRenderer
from marko.element import Element
from marko.block import Document, BlockElement
from marko.inline import InlineElement, LineBreak, RawText, Literal
import re

class SectionExtractor:
    def __init__(self):
        self.parser = marko.Parser()
        self.renderer = MarkdownRenderer()

    def extract_sections(self, markdown_text):
        document = self.parser.parse(markdown_text)
        sections = self._extract_sections(document)
        return sections

    def extract_sections_all(self, markdown_text):
        document = self.parser.parse(markdown_text)
        sections = self._extract_sections_all(document)
        return sections
    
    def reapply_sections(self, markdown_text, sections: dict[str, List[str]]) -> str:
        document = self.parser.parse(markdown_text)
        return self._reapply_sections(document, sections)
    
    def _extract_sections_all(self, document: Document):
        sections: dict[str, List[str]] = {}
        section_name = '_start'
        sections[section_name] = []
        for child in document.children:
            if not isinstance(child, BlockElement):
                continue
            block_child: BlockElement = child
            section_type = block_child.get_type(True)
            if section_type == 'heading':
                heading_child = block_child.children[0]
                if heading_child.get_type(True) == "raw_text":
                    current_section_name = self.renderer.render(heading_child)
                    if current_section_name:
                        section_name = current_section_name
                        sections[section_name] = []
                        continue
            elif section_type == 'paragraph':
                content = self.renderer.render(block_child)
                if content:
                    sections[section_name].append(content)
            elif section_type == 'list':
                for list_item in block_child.children:
                    list_item_content = self.renderer.render(list_item)
                    if list_item_content:
                        sections[section_name].append(list_item_content)
        return sections

    def _extract_sections(self, document: Document):
        sections: dict[str, List[str]] = {}
        section_name = '_start'
        section_building = False
        for child in document.children:
            if not isinstance(child, BlockElement):
                continue
            block_child: BlockElement = child
            section_type = block_child.get_type(True)
            if section_type == 'heading':
                heading_child = block_child.children[0]
                heading_child_type = heading_child.get_type(True)
                if heading_child_type== "raw_text":
                    current_section_name = self.renderer.render(heading_child)
                    if current_section_name == 'Arguments':
                        section_building = True
                        continue
            if section_building:
                if section_type == 'heading':
                    heading_child = block_child.children[0]
                    if heading_child.get_type(True) == "raw_text":
                        current_section_name = self.renderer.render(heading_child)
                        if current_section_name:
                            if current_section_name == 'Conclusion':
                                section_building = False
                                continue
                            else:
                                section_name = current_section_name
                                sections[section_name] = []
                elif section_type == 'paragraph':
                    content_segments = [self.renderer.render(paragraph_child) for paragraph_child in block_child.children]
                    content = "\n".join([x for x in content_segments if x is not None])
                    if content:
                        sections[section_name].append(content)
                elif section_type == 'list':
                    for list_item in block_child.children:
                        list_item_content = self.renderer.render(list_item)
                        if list_item_content:
                            sections[section_name].append(list_item_content)
        return sections
    
    def _reapply_sections(self, document: Document, sections: dict[str, List[str]]) -> str:
        section_building = False
        new_document = Document()
        new_document.children = []
        for child in document.children:
            if not isinstance(child, BlockElement):
                continue
            block_child: BlockElement = child 
            section_type = block_child.get_type(True)
            if not section_building:
                new_document.children.append(block_child)
                if section_type == 'heading':
                    heading_child = block_child.children[0]
                    heading_child_type = heading_child.get_type(True)
                    if heading_child_type== "raw_text":
                        current_section_name = self.renderer.render(heading_child)
                        if current_section_name == 'Arguments':
                            section_building = True
                            continue
            if section_building:
                if section_type == 'heading':
                    new_document.children.append(block_child)
                    heading_child = block_child.children[0]
                    if heading_child.get_type(True) == "raw_text":
                        current_section_name = self.renderer.render(heading_child)
                        if current_section_name:
                            if current_section_name == 'Conclusion':
                                section_building = False
                                continue
                            section_name = current_section_name
                            values = sections[section_name]
                            if values:
                                values.append('\n')
                                for value in values:
                                    sub_doc = self.parser.parse('\n'+value)
                                    for sub_child in sub_doc.children:
                                        new_document.children.append(sub_child)

        return self.renderer.render(new_document)
    
def get_substatements(statement: str) -> Generator[tuple[str, str], None, None]:
    """
    Extracts the sub-statement from the given statement.

    :param statement: The statement to extract from.
    :return: The extracted sub-statement.
    """
    HEADER_PATTERN = re.compile(r'^(?:\*{1,3}|_{1,3})?.+?:(?:\*{1,3}|_{1,3})?$')
    section_extractor = SectionExtractor()
    extractions = section_extractor.extract_sections_all(statement)
    extraction_statements = [x for sublist in extractions.values()
                                if sublist and len(sublist) > 0
                                for x in sublist]
    if len(extraction_statements) > 0:
        last_instructional_statement = ""
        for i in range(len(extraction_statements)):
            input_statement = extraction_statements[i]
            if not input_statement:
                continue
            # remove any ending carriage returns, newlines, or tabs
            input_statement = input_statement.strip()
            # match optional 1–3 asterisks or underscores at start/end, ending with a colon
            
            if HEADER_PATTERN.match(input_statement):
                last_instructional_statement = f"{last_instructional_statement} {input_statement}".strip()
                continue
            # optimize bullet prefix handling by using a tuple in startswith
            if input_statement.startswith(('*', '-', '•')):
                input_statement = f"{last_instructional_statement} {input_statement}"
            else:
                last_instructional_statement = ""

            yield input_statement, extraction_statements[i]
