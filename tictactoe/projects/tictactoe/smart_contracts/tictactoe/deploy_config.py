import logging

import algokit_utils
from algosdk.v2client.algod import AlgodClient
from algosdk.v2client.indexer import IndexerClient
from algokit_utils import (
    EnsureBalanceParameters,
    TransactionParameters,
    ensure_funded,
    get_localnet_default_account,
)
from smart_contracts.artifacts.tictactoe.tic_tac_toe_client import TicTacToeClient
from algokit_utils.beta.algorand_client import AlgorandClient
import base64

import algosdk.abi
import pytest
from algokit_utils import (
    EnsureBalanceParameters,
    TransactionParameters,
    ensure_funded,
    get_localnet_default_account,
)
from algokit_utils.beta.account_manager import AddressAndSigner
from algokit_utils.beta.algorand_client import AlgorandClient
from algokit_utils.beta.client_manager import AlgoSdkClients
from algokit_utils.beta.composer import PayParams
from algosdk.atomic_transaction_composer import TransactionWithSigner
from algosdk.util import algos_to_microalgos
from algosdk.v2client.algod import AlgodClient
from algosdk.v2client.indexer import IndexerClient

from smart_contracts.artifacts.tictactoe.tic_tac_toe_client import TicTacToeClient

logger = logging.getLogger(__name__)

# define deployment behaviour based on supplied app spec
def deploy(
    algod_client: AlgodClient,
    indexer_client: IndexerClient,
    app_spec: algokit_utils.ApplicationSpecification,
    deployer: algokit_utils.Account,
) -> None:
    from smart_contracts.artifacts.tictactoe.tic_tac_toe_client import (
        TicTacToeClient,
    )

    app_client = TicTacToeClient(
        algod_client,
        creator=deployer,
        indexer_client=indexer_client,
    )

    app_client.deploy(
        on_schema_break=algokit_utils.OnSchemaBreak.AppendApp,
        on_update=algokit_utils.OnUpdate.AppendApp,
    )

    last_game_id = app_client.get_global_state().id_counter
    algorand = AlgorandClient.from_clients(AlgoSdkClients(algod_client, indexer_client))
    algorand.set_suggested_params_timeout(0)

    host = algorand.account.random()
    ensure_funded(
        algorand.client.algod,
        EnsureBalanceParameters(
            account_to_fund=host.address,
            min_spending_balance_micro_algos=algos_to_microalgos(200_000),
        ),
    )
    print(f"balance of host address: ",algod_client.account_info(host.address)["amount"]);
    print(f"host address: ",host.address);
    ensure_funded(
        algorand.client.algod,
        EnsureBalanceParameters(
            account_to_fund=app_client.app_address,
            min_spending_balance_micro_algos=algos_to_microalgos(10_000),
        ),
    )
    print(f"app_client address: ",app_client.app_address);

    # app_client.new_game(
    #     mbr=TransactionWithSigner(
    #         txn=algorand.transactions.payment(
    #             PayParams(
    #                 sender=host.address,
    #                 receiver=app_client.app_address,
    #                 amount=2_500 + 400 * (5 + 8 + 75),
    #             )
    #         ),
    #         signer=host.signer,
    #     ),
    #     transaction_parameters=TransactionParameters(
    #         signer=host.signer,
    #         sender=host.address,
    #         boxes=[(0, b"games" + (last_game_id + 1).to_bytes(8, "big"))],
    #     ),
    # )

    game_id = app_client.opt_in_new_game(
        mbr=TransactionWithSigner(
            txn=algorand.transactions.payment(
                PayParams(
                    sender=host.address,
                    receiver=app_client.app_address,
                    amount=2_500 + 400 * (5 + 8 + 75),
                )
            ),
            signer=host.signer,
        ),
        transaction_parameters=TransactionParameters(
            signer=host.signer,
            sender=host.address,
            boxes=[(0, b"games" + (last_game_id + 1).to_bytes(8, "big"))],
        ),
    )
    
    guest = algorand.account.random()
    ensure_funded(
        algorand.client.algod,
        EnsureBalanceParameters(
            account_to_fund=guest.address,
            min_spending_balance_micro_algos=algos_to_microalgos(10),
        ),
    )

    app_client.opt_in_join(
        game_id=game_id.return_value,
        transaction_parameters=TransactionParameters(
            signer=guest.signer,
            sender=guest.address,
            boxes=[(0, b"games" + game_id.return_value.to_bytes(8, "big"))],
        ),
    )

    moves = [
        ((0, 0), (2, 2)),
        ((1, 1), (2, 1)),
        ((0, 2), (2, 0)),
    ]

    

    for host_move, guest_move in moves:
        app_client.move(
            game_id=game_id.return_value,
            x=host_move[0],
            y=host_move[1],
            transaction_parameters=TransactionParameters(
                signer=host.signer,
                sender=host.address,
                boxes=[(0, b"games" + game_id.return_value.to_bytes(8, "big"))],
                accounts=[guest.address],
            ),
        )

        # app_client.join(game_id=game_id.return_value)

        app_client.move(
            game_id=game_id.return_value,
            x=guest_move[0],
            y=guest_move[1],
            transaction_parameters=TransactionParameters(
                signer=guest.signer,
                sender=guest.address,
                boxes=[(0, b"games" + game_id.return_value.to_bytes(8, "big"))],
                accounts=[host.address],
            ),
        )

    game_state = algosdk.abi.TupleType(
        [
            algosdk.abi.ArrayStaticType(algosdk.abi.ByteType(), 9),
            algosdk.abi.AddressType(),
            algosdk.abi.AddressType(),
            algosdk.abi.BoolType(),
            algosdk.abi.UintType(8),
        ]
    ).decode(
        base64.b64decode(
            algorand.client.algod.application_box_by_name(
                app_client.app_id, box_name=b"games" + game_id.return_value.to_bytes(8, "big")
            )["value"]
        )
    )
    assert game_state[3]

    assert app_client.get_local_state(host.address).games_played == 1
    assert app_client.get_local_state(guest.address).games_played == 1

    assert app_client.get_local_state(host.address).games_won == 0
    assert app_client.get_local_state(guest.address).games_won == 1
    suggested_params = algod_client.suggested_params()
    suggested_params.fee = 1000 

    # app_client.delete_game(
    #     game_id=game_id.return_value,
    #     transaction_parameters=TransactionParameters(
    #         signer=host.signer,
    #         sender=host.address,
    #         boxes=[(0, b"games" + game_id.return_value.to_bytes(8, "big"))],
    #         accounts=[host.address],
    #         suggested_params=suggested_params,
    #     ),
    # )
    # print(f"Game with ID {game_id.return_value} deleted.")
