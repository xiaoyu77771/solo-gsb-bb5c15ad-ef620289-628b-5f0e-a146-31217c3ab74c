class EventConflictError(Exception):
    """相同序号但温度/事件时间与已存储内容不一致。"""

    def __init__(self, box_code: str, seq: int):
        self.box_code = box_code
        self.seq = seq
        super().__init__(
            f"箱子 {box_code} 的序号 {seq} 已存在但内容不同，事件被拒绝"
        )
