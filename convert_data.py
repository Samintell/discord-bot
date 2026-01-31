import json
import sys
import requests
import os
import cutlet
import time
from urllib.parse import quote

def read_json(file_path):
    """Read data from a JSON file."""
    with open(file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)
    return data

def write_json(data, file_path):
    """Write data to a JSON file."""
    with open(file_path, 'w') as file:
        json.dump(data, file, indent=4)

def clean_filename(name):
    """Clean the filename by removing or replacing invalid characters."""
    invalid_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
    for char in invalid_chars:
        name = name.replace(char, '_')
    return name

def get_english_translation(title, artist, song_id):
    """Try to get English translation for a song title."""
    # Simple heuristic: if title is already in English (mostly ASCII), return it
    if all(ord(c) < 128 for c in title):
        return title
    
    # Check common known translations (you can expand this dictionary)
    known_translations = {
        # Vocaloid hits
        '君の知らない物語': 'The Story You Don\'t Know',
        '千本桜': 'Senbonzakura',
        '天ノ弱': 'Ama no Jaku',
        'からくりピエロ': 'Karakuri Pierrot',
        '脳漿炸裂ガール': 'Brain Fluid Explosion Girl',
        'シュガーソングとビターステップ': 'Sugar Song and Bitter Step',
        '夜咄ディセイブ': 'Night Talk Deceive',
        'ローリンガール': 'Rolling Girl',
        'いーあるふぁんくらぶ': '1 2 Fan Club',
        '裏表ラバーズ': 'Ura-Omote Lovers',
        '弱虫モンブラン': 'Coward Mont Blanc',
        'モザイクロール': 'Mozaik Role',
        '二息歩行': 'Two Breaths Walking',
        'セツナトリップ': 'Setsuna Trip',
        'ぽっぴっぽー': 'PoPiPo',
        'アゲアゲアゲイン': 'Age Age Again',
        '言ノ葉カルマ': 'Kotonoha Karma',
        'リリリリ★バーニングナイト': 'Lily Lily Burning Night',
        'マトリョシカ': 'Matryoshka',
        'メルト': 'Melt',
        'ワールドイズマイン': 'World is Mine',
        '初音ミクの消失': 'The Disappearance of Hatsune Miku',
        '深海少女': 'Deep Sea Girl',
        '炉心融解': 'Meltdown',
        'サイハテ': 'Saihate',
        '恋は戦争': 'Love is War',
        'ダブルラリアット': 'Double Lariat',
        'ブラック★ロックシューター': 'Black Rock Shooter',
        'え？あぁ、そう。': 'Eh? Ah, Sou.',
        'ゴーストルール': 'Ghost Rule',
        'ロストワンの号哭': 'Lost One\'s Weeping',
        '金曜日のおはよう': 'Friday\'s Good Morning',
        'エイリアンエイリアン': 'Alien Alien',
        'テレキャスタービーボーイ': 'Telecaster B-Boy',
        'アンハッピーリフレイン': 'Unhappy Refrain',
        'ローリンガール': 'Rolling Girl',
        'リモコン': 'Remote Control',
        'メランコリック': 'Melancholic',
        '恋愛裁判': 'Love Trial',
        'ドレミファロンド': 'Do-Re-Mi-Fa Rondo',
        'うそつき': 'Liar',
        'パンダヒーロー': 'Panda Hero',
        'ヒビカセ': 'Hibikase',
        'イヤイヤ星人': 'Iya Iya Star',
        '威風堂々': 'Pomp and Circumstance',
        'カゲロウデイズ': 'Kagerou Daze',
        'チルドレンレコード': 'Children Record',
        'アヤノの幸福理論': 'Ayano\'s Theory of Happiness',
        '如月アテンション': 'Kisaragi Attention',
        'ロスタイムメモリー': 'Lost Time Memory',
        'オツキミリサイタル': 'Otsukimi Recital',
        '夏恋花火': 'Summer Love Fireworks',
        'アウターサイエンス': 'Outer Science',
        'コノハの世界事情': 'Konoha\'s State of the World',
        'メズマライザー': 'Mesmerizer',
        'ずんだもんの朝食　〜目覚ましずんラップ〜': 'Zundamon\'s Breakfast ~Alarm Clock Zunda Rap~',
        
        # Touhou
        '魔理沙は大変なものを盗んでいきました': 'Marisa Stole the Precious Thing',
        'ナイト・オブ・ナイツ': 'Night of Knights',
        '幽雅に咲かせ、墨染の桜': 'Bloom Nobly, Cherry Blossoms of Sumizome',
        'ネクロファンタジア': 'Necro Fantasia',
        '竹取飛翔': 'Lunatic Princess',
        '月に叢雲華に風': 'Broken Moon',
        'エクステンドアッシュ': 'Extend Ash',
        'ウサテイ': 'U.N. Owen Was Her?',
        '患部で止まってすぐ溶ける～狂気の優曇華院': 'Tamusic - Rabbit Jumping',
        '全人類ノ非想天則': 'Zengen Banrai',
        '放課後ストライド': 'After School Stride',
        'しゅわスパ大作戦☆': 'Shuwa Spa Strategy',
        '待チ人ハ来ズ。': 'The Expected One Will Not Come',
        '幻想のサテライト': 'Satellite of Fantasy',
        'sweet little sister': 'Sweet Little Sister',
        'お嫁にしなさいっ！': 'Marry Me!',
        '最速最高シャッターガール': 'Fastest Highest Shutter Girl',
        '林檎華憐歌': 'Ringo Kuren Ka',
        
        # Anime
        '紅蓮華': 'Gurenge',
        '残酷な天使のテーゼ': 'A Cruel Angel\'s Thesis',
        'タッチ': 'Touch',
        'ウィーアー！': 'We Are!',
        '白金ディスコ': 'Platinum Disco',
        'only my railgun': 'Only My Railgun',
        'secret base ～君がくれたもの～': 'Secret Base',
        'コネクト': 'Connect',
        '君じゃなきゃダメみたい': 'It Has to Be You',
        'チェリーハント': 'Cherry Hunt',
        'オラシオン': 'Oracion',
        'Rising Hope': 'Rising Hope',
        'crossing field': 'Crossing Field',
        'シリウス': 'Sirius',
        'イマジネーション': 'Imagination',
        '創聖のアクエリオン': 'Genesis of Aquarion',
        'ライオン': 'Lion',
        'God knows...': 'God Knows',
        '雪、無音、窓辺にて。': 'Snow, Silence, By the Window',
        'どんなときも。': 'Donna Toki mo',
        '世界が終るまでは…': 'Until the World Ends',
        '夏祭り': 'Summer Festival',
        'さくらんぼ': 'Cherry',
        '天体観測': 'Tentai Kansoku',
        
        # Japanese Pop/Rock
        'ハナミズキ': 'Hanamizuki',
        '花束を君に': 'Hanataba wo Kimi ni',
        'Lemon': 'Lemon',
        '糸': 'Ito',
        'プラネタリウム': 'Planetarium',
        'やさしさに包まれたなら': 'If Wrapped in Tenderness',
        '恋': 'Koi',
        '海の声': 'Umi no Koe',
        '前前前世': 'Zenzenzense',
        'うっせぇわ': 'Usseewa',
        'ドライフラワー': 'Dried Flowers',
        '夜に駆ける': 'Racing into the Night',
        '怪物': 'Monster',
        '炎': 'Homura',
        'ヒバリ': 'Skylarks',
        'アンダーキッズ': 'Under Kids',
        
        # Common terms
        '鼓動': 'Heartbeat',
        'キズナの物語': 'Story of Bonds',
        '円舞曲、君に': 'Waltz for You',
        'ココロスキャンのうた': 'Kokoro Scan Song',
        'ぐるぐるWASH！コインランドリー・ディスコ': 'Guru Guru WASH! Coin Laundry Disco',
        'みんなのマイマイマー': 'Everyone\'s MaiMai March',
        'かせげ！ジャリンコヒーロー': 'Earn! Jarinko Hero',
        'コトバ・カラフル': 'Colorful Words',
        'きゅびずむ': 'Cubism',
        'きゅびびびびずむ': 'Cubibibibism',
        'ロールプレイングゲーム': 'Role-Playing Game',
        'グッバイ宣言': 'Goodbye Declaration',
        'アマノジャクリバース feat. ｙｔｒ' : 'Amanojaku Reverse',
        '泥の分際で私だけの大切を奪おうだなんて': 'Even Though I\'m Just Mud, Don\'t Take Away What\'s Important to Me',
        'チルノのパーフェクトさんすう教室　⑨周年バージョン': 'Cirno\'s Perfect Math Class 9th Anniversary Version',
        'スカーレット警察のゲットーパトロール24時': 'Scarlet Police Ghetto Patrol 24 Hours',
        'バカ通信': 'Idiotic Transaction',
        'み　む　かｩ　わ　ナ　イ　ス　ト　ラ　イ　ク': 'Mimukauwa Nice Try',
        'Don\'t Fight The Music': 'donfai',
        '神っぽいな': 'God-ish',
        'Seyana. ～何でも言うことを聞いてくれるアカネチャン～': 'Seyana.',
        '寝起きヤシの木': 'Waking Yashinoki',
        'あなたは世界の終わりにずんだを食べるのだ': 'You will eat Zunda at the end of the world',
        'ライアーダンサー': 'Liar Dancer',
        '悪戯センセーション': 'Mischievious Sensation',
        '拝啓、最高の思い出たち': 'Dear my sweet memories',
        'キミノヨゾラ哨戒班': 'Night Sky Patrol of Tomorrow'
    }
    
    if title in known_translations:
        return known_translations[title]
    
    # For songs we don't have translations for, return empty string
    # Could potentially expand this with API calls to translation services
    return ''

def get_romaji_override(title):
    """Override romaji for titles with special characters that cause conversion failures."""
    romaji_overrides = {
        # English titles with special characters
        'Daydream café': 'Daydream cafe',
        'Sweets×Sweets': 'Sweets x Sweets',
        'L\'épilogue': 'L\'epilogue',
        'D\u272aN\u2019T  ST\u272aP  R\u272aCKIN\u2019': 'Don\'t Stop Rockin\'',
        'WARNING×WARNING×WARNING': 'WARNING x WARNING x WARNING',
        'GRÄNDIR': 'GRANDIR',
        'Jörqer': 'Jorqer',
        'GIGANTØMAKHIA': 'GIGANTOMAKHIA',
        'sølips': 'solips',
        'Mjölnir': 'Mjolnir',
        'Löschen': 'Loschen',
        '\u212bntinomi\u03b5': 'Antinomie',
        'グッバイ宣言': 'Goodbye Sengen',
        # Japanese/Chinese titles with problematic characters
        '紅星ミゼラブル～廃憶編': 'Kurenai Hoshi Miserable ~Haioku Hen~',
        '康莊大道': 'Kang Zhuang Da Dao',
        '勦滅': 'Soumetsu',
        'ねぇ、壊れタ人形ハ何処へ棄テらレるノ？': 'Nee, Kowareta Ningyou wa Doko e Suterareru no?',
        '殿ッ！？ご乱心！？': 'Tono! ? Goranshin! ?',
        'プリズム△▽リズム': 'Prism Rhythm',
        'ばかみたい【Taxi Driver Edition】': 'Baka Mitai',
        'ヴィラン': 'Villain',
        'False Amber (from the Black Bazaar, Or by A Kervan Trader from the Lands Afar, Or Buried Beneath the Shifting Sands That Lead Everywhere but Nowhere)': 'False Amber',
        'パラマウント☆ショータイム！！': 'Paramount Showtime!!',
        'VeRForTe αRtE:VEiN': 'Verforte Arte Vein',
        '系ぎて': 'Tsunagite',
        '独りんぼエンヴィー ': 'Hitorinbo Envy',
        'テリトリーバトル': 'Territory Battle',
        'キャットラビング': 'Cat Loving',
        'ミルキースター・シューティングスター': 'Milky Star, Shooting Star',
        'ヘビーローテーション': 'Heavy Rotation',
        'ゼロトーキング': 'Zero Talking',
        '人生リセットボタン': 'Jinsei Reset Button',
        'ピリオドサイン': 'Period Sign',
        'スロウダウナー': 'Slow Downer',
        'リフヴェイン': 'Rifvein',
        '悪戯センセーション': 'Itazura Sensation',
        'アイデンティティ': 'Identity',
        'パラボラ': 'Parabola',
        'ジレンマ': 'Dilemma',
        '幾望の月': 'Kibou no Tsuki',
        '言ノ葉遊戯': 'Kotonoha Yugi',
        '明星ギャラクティカ': 'Myoujou Galactica',
        '最愛人生ランナー': 'Saiai Jinsei Runner',
        '神威': 'Kamui',
        'KHYMΞXΛ': 'KHYMEXA'
    }
    return romaji_overrides.get(title, None)

def main():
    output_file = 'output.json'
    data_url = 'https://dp4p6x0xfi5o9.cloudfront.net/maimai/data.json'

    # Download data from URL
    print(f"Downloading data from {data_url}...")
    try:
        response = requests.get(data_url)
        response.raise_for_status()
        data = response.json()
        print("Data downloaded successfully!")
    except requests.RequestException as e:
        print(f"Failed to download data: {e}")
        return

    katsu = cutlet.Cutlet()
    katsu.use_foreign_spelling = False

    chart_data = []
    failed_romaji = []  # Track titles with failed romaji conversion

    for song in data['songs']:

        # Ensure the directory for images exists
        image_dir = 'images'
        os.makedirs(image_dir, exist_ok=True)

        # Download and save the song image
        image_url = f"https://dp4p6x0xfi5o9.cloudfront.net/maimai/img/cover/{song['imageName']}"

        image_path = os.path.join(image_dir, clean_filename(song['songId']) + ".png")

        # Check if the image already exists to avoid re-downloading
        if os.path.exists(image_path):
            #print(f"Image for {song['imageName']} already exists at {image_path}, skipping download.")
            pass
        else:
            try:
                response = requests.get(image_url)
                response.raise_for_status()  # Raise an error for HTTP issues
                with open(image_path, 'wb') as img_file:
                    img_file.write(response.content)
                print(f"Downloaded image for {song['imageName']} to {image_path}")
            except requests.RequestException as e:
                print(f"Failed to download image {song['imageName']}: {e}")

        for chart in song['sheets']:
            if chart['difficulty'] == 'master' or chart['difficulty'] == 'remaster':
                image = clean_filename(song['songId']) + ".png"
                english_title = get_english_translation(song['title'], song['artist'], song['songId'])
                
                # Check for romaji override first
                romaji_override = get_romaji_override(song['title'])
                if romaji_override:
                    romaji = romaji_override
                else:
                    # Generate romaji, but if it contains multiple question marks (failed conversion), use original title
                    romaji = katsu.romaji(song['title'])
                # Check for conversion failure: multiple consecutive question marks or 2+ question marks in short text
                if '??' in romaji or romaji.count('?') >= 3:
                    # Track failed conversion
                    if song['title'] not in [f['title'] for f in failed_romaji]:
                        failed_romaji.append({
                            'title': song['title'],
                            'artist': song['artist'],
                            'romaji_attempted': romaji,
                            'song_id': song['songId']
                        })
                    romaji = song['title']
                
                chart_entry = {
                    'song_id': song['songId'],
                    'category': song['category'],
                    'title': song['title'],
                    'artist': song['artist'],
                    'version': chart['version'] if 'version' in chart else song.get('version', ''),
                    'type': chart['type'],
                    'difficulty': chart['difficulty'],
                    'level': chart['internalLevelValue'],
                    'image': image,
                    'romaji': romaji,
                    'english': english_title
                }
                chart_data.append(chart_entry)

    # Write data to the output JSON file
    write_json(chart_data, output_file)
    print(f"Data written to {output_file}")
    
    # Write failed romaji conversions to separate file
    if failed_romaji:
        failed_file = 'failed_romaji.json'
        write_json(failed_romaji, failed_file)
        print(f"\n⚠️  Found {len(failed_romaji)} titles with failed romaji conversion")
        print(f"Details written to {failed_file}")

if __name__ == "__main__":
    main()