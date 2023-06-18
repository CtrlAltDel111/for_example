import sqlite3 as sq
import json
import os
import sys

import pandas as pd
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from pydub import AudioSegment

from admin import AdminPanel
from artificialLib_v2 import Open_AI, Common, AudioAndTTS, Telegramm
from config import Config
from db import DB

pydub_path = 'C:\\LIB\\pydub-0.25.1\\pydub-0.25.1\\'
sys.path.append(pydub_path)
ffmpeg_path = 'C:\\LIB\\ffmpeg-snapshot\\ffmpeg'
sys.path.append(ffmpeg_path)
ffmpeg_path = 'C:\\ffmpeg\\bin'
sys.path.append(ffmpeg_path)


class it_support:
    def __init__(self):
        # config, database
        self.initial_db = DB(Config.COMMON_DB)
        self.conf = self.initial_db.update_conf()

        self.global_context = {self.conf.URL_TG_BOT: []}
        self.oai = Open_AI(self.conf, self.global_context)
        self.teleg = Telegramm(self.conf, self.global_context)
        self.aud = AudioAndTTS(self.conf)
        self.common = Common(self.conf)

        self.url_bot = self.conf.URL_TG_BOT
        self.bot = Bot(token=self.conf.TG_API_KEY)
        dp = Dispatcher(self.bot, storage=MemoryStorage())
        self.dp = dp

        self.role_name = 'it_support'
        self.keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
        self.btn1 = KeyboardButton('Open file')
        self.keyboard.add(self.btn1)

        self.tg_user = 'not'
        self.username = '_not'

        # Еще админ-панель
        self.admin_panel = AdminPanel(self.conf, self.initial_db, dp)


        # ------------------------------------------------------
        # Обработка файлов - в разработке
        @dp.message_handler(content_types=['document'])
        async def handle_xlsx_upload(message: types.Message):
            if not os.path.exists('common.db'):
                for name in self.conf.admins_id:
                    if str(name) == str(message.from_user.id):
                        # await self.bot.send_message(chat_id=message.from_user.id, text='Создаю базу данных')
                        await save_data_file(file=message.document, chat_id=message.chat.id,
                                             user_id=message.from_user.id)

        async def save_data_file(file: types.Document, chat_id, user_id):
            global num
            directory = str(user_id)
            if file.file_name.lower() == 'users.xlsx' or file.file_name.lower() == 'statistic.xlsx':  # endswith('.xlsx'):
                if not os.path.exists(directory):
                    os.makedirs(directory)
                await xlsx_to_db(user_id=user_id, chat_id=chat_id, file=file)
            else:
                await self.bot.send_message(chat_id=chat_id,
                                            text='некорректный документ. Используйте имя файла "users.xlsx" '
                                                 'для создания таблицы "users" или "statistic.xlsx" для '
                                                 'создания таблицы "statistic"')

        async def xlsx_to_db(file: types.Document, chat_id, user_id):
            directory = str(user_id)
            create_directory(directory)
            df = pd.read_excel(await self.bot.download_file_by_id(file.file_id), sheet_name=0)
            print(f'Dataframe:\n{df}\n')
            table = str(file.file_name)[:-5]
            print('Название таблицы:', table)
            database = 'main.db'
            conn = sq.connect(database)
            print('открыли соединение с базой')
            try:
                df.to_sql(name=table, con=conn, if_exists='replace', index=False)
                await self.bot.send_message(chat_id=chat_id,
                                            text=f'Создана таблица {table} в базе данных {database} с колонками:\n{df.columns.values}')
            except Exception as e:
                print('произошла ошибка при добавлении файла из df в базу:\n', e)
            conn.close()

        def create_directory(directory):
            if not os.path.exists(directory):
                os.makedirs(directory)

        # ---------------------------------------------------------------------------------------------

        @dp.chat_member_handler()
        async def send_invite(chat_member: types.ChatMemberUpdated):

            chat_id = chat_member.chat.id
            user_id = chat_member.from_user.id
            print('chat_id:', chat_id, 'user_id:', user_id)

        @dp.message_handler(commands=['start'])
        async def send_welcome(message: types.Message):
            await message.reply(self.conf.start_)

        @dp.message_handler(commands=['help'])
        async def help_fun(message: types.Message):
            await message.reply(self.conf.help_)

        # Работа с голосовыми сообщениями
        # В разработке
        # --------------------------------------------
        # @dp.message_handler(content_types=['voice'])
        # async def echo_audio(message: types.Message):
        #     voice = await message.voice.get_file()
        #     file_path = message.from_user.username + "/voice/" + voice.file_unique_id
        #     await self.bot.download_file(voice.file_path, file_path + ".ogg", make_dirs=True)
        #     AudioSegment.from_file(file_path + ".ogg").export(file_path + ".mp3", format="mp3")
        #     transcript = self.aud.stt_process(file_path + ".mp3")
        #     json_tmp = json.dumps(transcript['text'], ensure_ascii=False).encode('utf8')
        #     answer = json_tmp.decode()
        #     message.text = answer
        #     # if self.conf.name_bot_ru in answer:
        #     #     print('AUDIO:', answer)
        #     # else:
        #     #     answer = self.conf.name_bot_ru + ' ' + answer
        #     if transcript['error']:
        #         await message.reply(answer)
        #     else:
        #         if message.chat.type == 'private':
        #             await main_fun(message)
        #         else:
        #             await group_main_fun(message)

        # ---------------------------------------------

        def add_new_user(message: types.Message):
            if not self.initial_db.get_user(message.from_user.id):
                self.initial_db.create_user(message.from_user.id, message.from_user.username,
                                            message.from_user.first_name, message.from_user.last_name,
                                            '')
            if not self.initial_db.get_membership_by_bot_and_user(self.dp.bot.id, message.from_user.id):
                self.initial_db.create_membership(message.from_user.id, self.dp.bot.id,
                                                  'user', '', '', '',
                                                  self.conf.message_count_limit)

        async def user_check(message: types.Message):
            check = True
            if self.conf.check_follow:
                # Group Follower Check
                if not self.initial_db.check_follow_for_user_to_group(self.conf.group, message.from_user.id):
                    await message.answer(f"Вы не подписаны на группу: {self.conf.URL_TG_GROUP}")
                    check = False
            if self.conf.check_subscribe:
                # Subscriber Check
                if not self.initial_db.check_member_is_subscriber(dp.bot.id, message.from_user.id):
                    await message.answer("Ваша подписка истекла")
                    check = False
            if self.conf.message_count_limit > 0:
                # Limit Check
                if self.initial_db.get_member_count_message(dp.bot.id, message.from_user.id) == 0:
                    await message.answer("Закончились бесплатные личные сообщения")
                    check = False
            return check

        # Личные сообщения боту
        # ------------------------------
        @dp.message_handler(chat_type=[types.ChatType.PRIVATE], state='*')
        async def main_fun(message: types.Message, state: FSMContext):
            print('chat_id:', message.chat.id)
            print('user_id:', message.from_user.id)
            print('message:', message.text)

            # Проверка на приход с каким-то state
            if not await state.get_state() is None:
                await state.finish()
                message = types.Update(
                    update_id=123,
                    chat=message.chat,
                    message=message
                )
                await dp.process_update(message)
                return
            # Добавление нового пользователя в базу
            add_new_user(message)

            # Admins work in progress
            if self.admin_panel.isActive:
                await message.answer("Извините, бот пока не доступен. Идут технические работы.")
                return

            # user is Admin?
            if not (message.from_user.id in self.conf.admins_id):
                if not await user_check(message):
                    return

            MESSAGE = message.text
            username = message.from_user['username']  # По факту User_ID
            if username is None:
                username = 'Id_' + str(message.from_user.id)
            if 'очисти контекст' in MESSAGE or 'отчисти контекст' in MESSAGE:
                self.global_context.update({username: []})
            if username not in self.global_context:
                self.global_context.update({username: []})

            res_answer = await self.turbo_chat(self.role_name, username, MESSAGE)
            self.oai.context_add(username, "quest:" + MESSAGE + " answer:" + res_answer)
            if not (message.from_user.id in self.conf.admins_id) and self.conf.message_count_limit > 0:
                self.initial_db.dec_member_count_message(dp.bot.id, message.from_user.id)
            # print('CONTEXT:', username, ' | ', self.global_context[username])
            #
            # token_count = self.oai.get_count_token('\n'.join(self.global_context[username]))
            # print('USER_ID:|', message.from_user.id, '| TOKEN_CNT:', token_count)
            # print('MESSAGE:', MESSAGE)
            # print('ANSWER:', res_answer)
            await message.answer(res_answer)

        # Групповое общение с ботом
        @dp.message_handler()
        async def group_main_fun(message: types.Message):
            chat_id = message.chat.id
            user_id = message.from_user.id

            # We can't answer in chat?
            if not self.conf.has_group:
                return

            await self.to_follow(message)

            # Admins work in progress
            if self.admin_panel.isActive:
                await message.answer("Извините, бот пока не доступен. Идут технические работы.")
                return

            print('chat_id:', chat_id)
            print('user_id:', user_id)
            print('message:', message.text)
            answer_type = 'reply'

            if not self.initial_db.check_supported_groups(dp.bot.id, chat_id):
                print('unsupported chat')
                return

            MESSAGE = message.text
            MESSAGE, check = self.teleg.check_valid_message_v1(MESSAGE, self.conf.name_bot_en, self.conf.name_bot_ru, 'answer')
            if not check and message.reply_to_message is None:
                return
            if not (message.reply_to_message is None):
                if message.reply_to_message.from_user.username != (await dp.bot.me).username:
                    return

            username = message.from_user.username
            if username is None:
                username = 'Id_' + str(message.from_user['id'])
            # if username not in self.buffer:
            #     self.buffer.update({username: []})
            if username not in self.global_context:
                self.global_context.update({username: []})

            res_answer = await self.turbo_chat(self.role_name, username, MESSAGE)
            self.oai.context_add(username, "quest:" + MESSAGE + " answer:" + res_answer)

            if answer_type == 'answer':
                await message.answer(res_answer)
            else:
                await message.reply(res_answer)

    # ======================================================================================================================

    def role(self, role_type, username, request):
        _role = []
        _context = ''.join(self.global_context[username])
        token_count = self.oai.get_count_token(_context) + self.oai.get_count_token(request)
        while token_count > 2000 and self.global_context[username] != []:
            el = self.global_context[username].pop(0)
            print('Del:', el)
            # self.role(role_type, username, request)
            _context = ''.join(self.global_context[username])
            token_count = self.oai.get_count_token(_context) + self.oai.get_count_token(request)
        if role_type == self.role_name:
            _role = [
                {"role": "system",
                 "content": self.conf.prompt + '\n' + _context},
                {"role": "user", "content": f"{request}"}
            ]
        return _role

    def turbo_chat(self, role_type, username, request):
        _message = self.role(role_type, username, request)
        answer = self.oai.requestOpenAI(_message)
        return answer

    async def to_follow(self, message: types.Message):
        if not self.initial_db.check_follow_for_user_to_group(message.chat.id, message.from_user.id):
            if not self.initial_db.get_user(message.from_user.id):
                self.initial_db.create_user(message.from_user.id, message.from_user.username,
                                            message.from_user.first_name, message.from_user.last_name,
                                            '')
            if not self.initial_db.get_membership_by_bot_and_user(self.dp.bot.id, message.from_user.id):
                self.initial_db.create_membership(message.from_user.id, self.dp.bot.id,
                                                  'follower', '', '', '',
                                                  self.conf.message_count_limit)
            else:
                if self.initial_db.get_membership_by_bot_and_user(self.dp.bot.id, message.from_user.id)[2] == 'user':
                    self.initial_db.update_membership(message.from_user.id, self.dp.bot.id,
                                                      'follower', '', '', '',
                                                      self.conf.message_count_limit)
            self.initial_db.create_follower(message.from_user.id, message.chat.id)


if __name__ == '__main__':
    eii = it_support()
    executor.start_polling(eii.dp, skip_updates=True)
