import sys

class MockComputeModule(object):
    def __getattr__(self, name):
        # 어떤 속성 요청이 들어오든 빈 람다 함수를 리턴하여 AttributeError를 방지합니다.
        return lambda *args, **kwargs: None

sys.modules[__name__] = MockComputeModule()
