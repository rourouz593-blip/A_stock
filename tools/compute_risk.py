from _dispatch import expose

expose(globals(), "position_advisor", "compute_risk.py")
if __name__ == "__main__":
    main()
