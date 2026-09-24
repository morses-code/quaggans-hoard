"""Synthetic recipe data used only to test allocation and render documentation."""


def node(item_id, name, ingredients=None, icon=None):
    return {'id': item_id, 'name': name, 'ingredients': ingredients or [],
            'icon': icon, 'source': f'https://example.invalid/items/{item_id}', 'note': ''}


PROJECT_CATALOG = {'root': 30698, 'name': 'The Bifrost', 'nodes': {}}
PROJECT_CATALOG['nodes'] = {str(row['id']): row for row in [
    node(30698, 'The Bifrost', [{'id': 29180, 'count': 1}, {'id': 19654, 'count': 1},
                                {'id': 19626, 'count': 1}, {'id': 19674, 'count': 1}],
         'https://render.guildwars2.com/file/FD221A90427ADBD29B7E2DF8BDAF98BB16391162/456025.png'),
    node(29180, 'The Legend', icon='https://render.guildwars2.com/file/DA7AF6E3D970799A7847B3F10801FC1C1E98109E/1206503.png'),
    node(19654, 'Gift of The Bifrost', [{'id': 24277, 'count': 250}, {'id': 19676, 'count': 100}, {'id': 19623, 'count': 1}],
         'https://render.guildwars2.com/file/38C9C5C8F3725C196149C01FAD009C9707080B92/455834.png'),
    node(19626, 'Gift of Fortune', [{'id': 24277, 'count': 250}, {'id': 19721, 'count': 250}, {'id': 19675, 'count': 77}],
         'https://render.guildwars2.com/file/62A0F109C444E275E966B9A903D63FFE99540BAD/455807.png'),
    node(19674, 'Gift of Mastery', [{'id': 24277, 'count': 250}, {'id': 19925, 'count': 250}],
         'https://render.guildwars2.com/file/D4E560D3197437F0010DB4B6B2DBEA7D58E9DC27/455854.png'),
    node(24277, 'Pile of Crystalline Dust'), node(19676, 'Icy Runestone'), node(19623, 'Gift of Energy'),
    node(19721, 'Glob of Ectoplasm'),
    node(19675, 'Mystic Clover', icon='https://render.guildwars2.com/file/FE9DC3E10D4B2AE16DADEB07CF28A058570E2EF3/455855.png'),
    node(19925, 'Obsidian Shard'), node(19976, 'Mystic Coin'),
]}
