"""
Нагрузка плагина SPP

1/2 документ плагина
"""
import datetime
import logging
import re
import time
from random import uniform

import dateparser
import dateutil.parser
import pytz
from selenium.common import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait

from src.spp.types import SPP_document


class IEEE:
    """
    Класс парсера плагина SPP

    :warning Все необходимое для работы парсера должно находится внутри этого класса

    :_content_document: Это список объектов документа. При старте класса этот список должен обнулиться,
                        а затем по мере обработки источника - заполняться.


    """

    SOURCE_NAME = 'ieee'
    _content_document: list[SPP_document]

    def __init__(self, webdriver, url: str, categories: tuple | list, max_count_documents: int = None,
                 last_document: SPP_document = None, *args, **kwargs):
        """
        Конструктор класса парсера

        По умолчанию внего ничего не передается, но если требуется (например: driver селениума), то нужно будет
        заполнить конфигурацию
        """
        # Обнуление списка
        self._content_document = []
        self._driver = webdriver
        self.URL = url
        self.CATEGORIES = categories
        self._max_count_documents = max_count_documents
        self._last_document = last_document
        self._wait = WebDriverWait(self._driver, timeout=20)

        # Логер должен подключаться так. Вся настройка лежит на платформе
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.debug(f"Parser class init completed")
        self.logger.info(f"Set source: {self.SOURCE_NAME}")
        ...

    def content(self) -> list[SPP_document]:
        """
        Главный метод парсера. Его будет вызывать платформа. Он вызывает метод _parse и возвращает список документов
        :return:
        :rtype:
        """
        self.logger.debug("Parse process start")
        try:
            self._parse()
        except Exception as e:
            self.logger.debug(f'Parsing stopped with error: {e}')
        else:
            self.logger.debug("Parse process finished")
        return self._content_document

    def _parse(self):
        """
                Метод, занимающийся парсингом. Он добавляет в _content_document документы, которые получилось обработать
                :return:
                :rtype:
                """
        # HOST - это главная ссылка на источник, по которому будет "бегать" парсер
        self.logger.debug(F"Parser enter to {self.HOST}")

        # ========================================
        # Тут должен находится блок кода, отвечающий за парсинг конкретного источника
        # -

        for page in self._encounter_pages():
            # Получение URL новой страницы
            for link in self._collect_doc_links(page):
                # Запуск страницы и ее парсинг
                self._parse_news_page(link)

    def _encounter_pages(self) -> str:
        _base = self.URL
        _cats = '&refinements=SubjectCategory:'

        _href = _base
        for category in self.CATEGORIES:
            _href += _cats + category

        _param = f'&pageNumber='
        page = 1
        while True:
            url = str(_href) + str(_param) + str(page)
            page += 1
            yield url

    def _collect_doc_links(self, url: str) -> list[str]:
        """
        Сбор ссылок из архива одного года
        :param url:
        :return:
        """
        try:
            self._initial_access_source(url)
            self._wait.until(ec.presence_of_all_elements_located((By.CLASS_NAME, 'List-results-items')))
        except Exception as e:
            raise NoSuchElementException() from e

        links = []

        try:
            articles = self._driver.find_elements(By.CLASS_NAME, 'List-results-items')
        except Exception as e:
            raise NoSuchElementException('list is empty') from e
        else:
            for i, el in enumerate(articles):
                try:
                    # _title = el.find_element(By.CLASS_NAME, 'text-md-md-lh').text
                    _web_link = el.find_element(By.CLASS_NAME, 'text-md-md-lh').find_element(By.TAG_NAME,
                                                                                             'a').get_attribute('href')
                except Exception as e:
                    raise NoSuchElementException(
                        'Страница не открывается или ошибка получения обязательных полей') from e
                else:
                    links.append(_web_link)
                # 'stats-SearchResults_DocResult_ViewMore'

        return links

    def _parse_news_page(self, url: str) -> None:

        self.logger.debug(f'Start parse document by url: {url}')

        try:
            self._initial_access_source(url, 3)

            _title = self._driver.find_element(By.CLASS_NAME, 'document-title').text  # Title: Обязательное поле
            pub_date_text = self._driver.find_element(By.CLASS_NAME, 'doc-abstract-pubdate').text.replace(
                'Date of Publication: ', '')
            _published = self.utc.localize(dateparser.parse(pub_date_text))
            _weblink = url
        except Exception as e:
            raise NoSuchElementException(
                'Страница не открывается или ошибка получения обязательных полей') from e
        else:
            document = SPP_document(
                None,
                _title,
                None,
                None,
                _weblink,
                None,
                {},
                _published,
                None,
            )
            try:
                _authors = self._driver.find_elements(By.XPATH, '/html/body/meta[@name="parsely-author"]')
                if _authors:
                    document.other_data['authors'] = []
                for author in _authors:
                    document.other_data['authors'].append(author.get_attribute('content'))
            except:
                self.logger.debug('There aren\'t the authors in the page')

            try:
                self._driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(4)
                el_text = self._wait.until(ec.presence_of_element_located((By.ID, 'BodyWrapper')))
                if el_text:
                    document.text = el_text.text
            except:
                self.logger.debug('There isn\'t a main text in the page')

            try:
                # container = self._wait.until(ec.presence_of_element_located((By.CLASS_NAME, 'document-accordion-section-container')))
                # self._wait.until(ec.element_to_be_clickable((By.ID, 'keywords-header'))).click()
                # ПОЧИНИТЬ
                items = self._driver.find_elements(By.CLASS_NAME, 'doc-keywords-list-item')
                if items:
                    document.other_data['keywords'] = {}
                for item in items:
                    try:
                        name = self._driver.find_elements(By.XPATH, 'strong')
                        els = item.find_elements(By.CLASS_NAME, 'stats-keywords-list-item')
                        if els:
                            document.other_data.get('keywords')[name] = []
                        for el in els:
                            document.other_data.get('keywords').get(name).append(el.text)
                    except Exception as e:
                        self.logger.debug(f'There isn\'t an items of the keywords in the article; {e}')
            except Exception as e:
                self.logger.debug(f'There aren\'t the keywords in the page: {e}')

            self.find_document(document)

    def _initial_access_source(self, url: str, delay: int = 2):
        self._driver.get(url)
        self.logger.debug('Entered on web page ' + url)
        time.sleep(delay)
        self._agree_cookie_pass()

    def _agree_cookie_pass(self):
        """
        Метод прожимает кнопку agree на модальном окне
        """
        cookie_agree_xpath = '//*[@id="onetrust-accept-btn-handler"]'

        try:
            cookie_button = self._driver.find_element(By.XPATH, cookie_agree_xpath)
            if WebDriverWait(self._driver, 5).until(ec.element_to_be_clickable(cookie_button)):
                cookie_button.click()
                self.logger.debug(F"Parser pass cookie modal on page: {self._driver.current_url}")
        except NoSuchElementException as e:
            self.logger.debug(f'modal agree not found on page: {self._driver.current_url}')

    @staticmethod
    def _find_document_text_for_logger(doc: SPP_document):
        """
        Единый для всех парсеров метод, который подготовит на основе SPP_document строку для логера
        :param doc: Документ, полученный парсером во время своей работы
        :type doc:
        :return: Строка для логера на основе документа
        :rtype:
        """
        return f"Find document | name: {doc.title} | link to web: {doc.web_link} | publication date: {doc.pub_date}"

    def find_document(self, _doc: SPP_document):
        """
        Метод для обработки найденного документа источника
        """
        if self._last_document and self._last_document.hash == _doc.hash:
            raise Exception(f"Find already existing document ({self._last_document})")

        if self._max_count_documents and len(self._content_document) >= self._max_count_documents:
            raise Exception(f"Max count articles reached ({self._max_count_documents})")

        self._content_document.append(_doc)
        self.logger.info(self._find_document_text_for_logger(_doc))
